"""Verification assessment and signed controller RPC. No Docker authority in the API."""

import json
import logging
import re
from app.core.config import settings
from app.schemas.phase6 import CheckSpec
from app.schemas.phase5 import NormalizationRule
from app.services.phase5_engine import canonical, digest, normalize, strict_adapter_object, reject_json_constant
from app.services.secret_redactor import get_secret_redactor
from app.services.sandbox_harness import HARNESS
from app.services.sandbox_protocol import approved_command, validate_check_profile
from app.services import sandbox_client

logger = logging.getLogger(__name__)


def configuration(target_stack=None):
    from app.services.verification_profiles import get_profile
    if target_stack is None:
        raise ValueError("An exact job target stack is required to select a verification profile")
    profile=get_profile(target_stack)
    image=profile['image']
    checks=[CheckSpec.model_validate(c).model_dump() for c in profile['checks']]
    adapter=profile['adapter']
    if not re.fullmatch(r"sha256:[a-f0-9]{64}",image):
        raise ValueError("Configure an immutable local image digest")
    if not validate_check_profile(checks, system=False, schema_required=any(c['category']=='schema' for c in checks)):
        raise ValueError("Configure real build, unit, integration, static, security, dependency, license, runtime and required schema checks")
    if not approved_command(adapter,adapter=True):
        raise ValueError("Unsafe or missing verification profile")
    return image,checks,adapter


async def verified_runtime_args():
    if settings.SANDBOX_RUNTIME not in {'docker-rootless', 'gvisor-rootless', 'e2b-microvm'}:
        raise ValueError("Sandbox runtime is unverified")
    info=await sandbox_client.health()
    selected=info['runtime']['selected_runtime']
    expected='runsc' if settings.SANDBOX_RUNTIME=='gvisor-rootless' else 'runc'
    if selected!=expected: raise ValueError("Actual runtime differs from selected policy")
    return ['--runtime='+selected]


async def local_image(image):
    info=await sandbox_client.health()
    if image not in info.get('images',[]):
        raise ValueError("Immutable image is not approved by the controller")
    return image


async def execute(files,cases,baseline_hash,*,system_checks=None,binding=None,frozen_profile=None):
    try:
        if frozen_profile:
            image=frozen_profile['image'];checks=frozen_profile['checks'];adapter=frozen_profile['adapter']
            if not validate_check_profile(checks, system=False, schema_required=any(c['category']=='schema' for c in checks)):
                raise ValueError('Frozen verification profile is incomplete')
        else:
            image,checks,adapter=configuration()
        if system_checks is not None:
            from app.schemas.phase7 import SystemCheck
            checks=[SystemCheck.model_validate(c).model_dump() for c in system_checks]
            if not validate_check_profile(checks, system=True, schema_required=any(c['category']=='schema' for c in checks)):
                raise ValueError("Complete administrator-approved system profile required")
            if not frozen_profile:
                raise ValueError("System verification must use the frozen target-stack profile")
        execution={'image':image,'runtime':frozen_profile['runtime'] if frozen_profile else settings.SANDBOX_RUNTIME,'timeout':frozen_profile.get('timeout',settings.PHASE6_SANDBOX_TIMEOUT) if frozen_profile else settings.PHASE6_SANDBOX_TIMEOUT,
            'files':files,'cases':[{k:c[k] for k in ('test_case_id','name','fixtures')} for c in cases],
            'checks':checks,'adapter':adapter}
        proof=await sandbox_client.execute(execution,binding)
        if proof.get('execution_purpose')!='VERIFICATION':
            raise ValueError('Diagnostic execution cannot count as independent verification')
        observed=proof['execution']
        if observed.get('exit_code')!=0 or not observed.get('observation') or not observed.get('cleanup',{}).get('container_absent'):
            raise ValueError(observed.get('error') or 'Independent sandbox execution/cleanup failed')
        fingerprint=digest({'execution':execution,'baseline_hash':baseline_hash})
        result=assess(observed['observation'],cases,checks,fingerprint,files=files,image_digest=observed['image_digest'])
        review=proof['review'];review_result=review.get('observation') or {'status':'BLOCKED','findings':[]}
        if review.get('exit_code')!=0 or not review.get('cleanup',{}).get('container_absent'):
            review_result={'status':'BLOCKED','findings':[]}
        scan=proof['image_scan']
        result.update(image_id=observed['image_digest'],container_name=observed['worker_id'],
            runtime_evidence=observed,independent_review={**review_result,'worker_id':review['worker_id'],
            'started_at':review['started_at'],'finished_at':review['finished_at']},image_scan=scan,
            independent_worker_id=proof['worker_id'],controller_lease_token=proof['lease_token'],
            controller_lease_generation=proof['lease_generation'],controller_lease_expires_at=proof['lease_expires_at'],controller_attestation=proof['attestation'])
        result['passed']=result['passed'] and review_result['status']=='PASS' and scan['status']=='PASS'
        if scan['status']!='PASS':
            result['checks'].append({'category':'image_security','check_kind':'image_security','status':scan['status'],
                'result':scan['status'],'exit_code':None,'tool_name':scan.get('tool','trivy'),
                'tool_version':scan.get('tool_version','NOT_RUN'),'image_digest':image,'skipped_reason':scan.get('reason')})
        return result
    except Exception as exc:
        logger.warning('sandbox blocked: %s',type(exc).__name__)
        return {'available':False,'passed':False,'reason':str(exc)[:700],'checks':[],'cases':[]}


def assess(data: dict, cases: list[dict], specs: list[dict], fingerprint: str, *, files: dict | None = None, image_digest: str | None = None) -> dict:
    """Host-side deterministic comparison; adapters never supply pass/fail or expected outputs."""
    try:
        if (
            set(data) != {"checks", "observations", "source_unchanged"}
            or len(data["checks"]) != len(specs)
            or len(data["observations"]) != len(cases)
        ):
            raise ValueError("Incomplete independent execution evidence")
        checks, results = [], []
        for item, spec in zip(data["checks"], specs):
            if (
                item["category"] != spec["category"]
                or item["command"] != spec["command"]
                or not isinstance(item["duration_ms"], (float, int))
            ):
                raise ValueError("Check evidence identity mismatch")
            status=item.get('status')
            if status not in {'PASS','FAIL','NOT_RUN','TIMEOUT','BLOCKED','NOT_APPLICABLE'}:
                status='PASS' if type(item.get('exit_code')) is int and item['exit_code']==0 else 'FAIL'
            if item.get('exit_code') is None:
                status='TIMEOUT' if status=='TIMEOUT' else 'NOT_RUN'
            if status=='PASS' and item['category'] in {'unit', 'integration', 'runtime', 'api_compatibility', 'schema'} and not item.get('case_count'):
                status='NOT_RUN'
            checks.append(
                {
                    **item,
                    "check_kind": item["category"],
                    "command_profile_digest": digest(spec),
                    "image_digest": image_digest,
                    "source_commit_hash": None,
                    "dependency_hashes": [],
                    "status": status,
                    "result": status,
                    "artifact_hash": fingerprint,
                }
            )
        for observed, case in zip(data["observations"], cases):
            if observed["test_case_id"] != case["test_case_id"]:
                raise ValueError("Frozen test evidence mismatch")
            actual = None
            match = False
            # Presence of an HTML route or asset cannot stand in for browser
            # behavior. Static-web behavior must be observed by the configured
            # target adapter (which may drive a browser/DOM harness).
            if type(observed.get("exit_code")) is int and observed["exit_code"] == 0:
                actual = json.loads(
                    observed["stdout"],
                    object_pairs_hook=strict_adapter_object,
                    parse_constant=reject_json_constant,
                )
                if not isinstance(actual, dict) or set(actual) != {
                    "output",
                    "side_effects",
                }:
                    raise ValueError("Target adapter observation contract violated")
                rules = [
                    NormalizationRule.model_validate(r) for r in case["normalization"]
                ]
                match = canonical(normalize(actual["output"], rules)) == canonical(
                    normalize(case["expected"], rules)
                ) and canonical(actual["side_effects"]) == canonical(
                    case["side_effects"]
                )
            results.append(
                {
                    "test_case_id": case["test_case_id"],
                    "actual": actual,
                    "status": "PASS" if match else "UNOBSERVED" if observed.get("status") == "UNOBSERVED" or observed.get("exit_code") is None else "FAIL",
                    "difference_classification": "NONE" if match else "UNOBSERVED" if observed.get("status") == "UNOBSERVED" or observed.get("exit_code") is None else "REGRESSION",
                    "command": observed["command"],
                    "exit_code": observed.get("exit_code"),
                    "duration_ms": observed["duration_ms"],
                    "artifact_hash": fingerprint,
                }
            )
        passed = (
            (bool(cases) if cases else bool(checks))
            and data["source_unchanged"] is True
            and all(c["status"] in {"PASS", "NOT_APPLICABLE"} for c in checks + results)
            and any(c["status"] == "PASS" for c in checks)
            and any(c["category"] == "build" and c["status"] == "PASS" for c in checks)
            and any(c["category"] == "security" and c["status"] == "PASS" for c in checks)
        )
        return get_secret_redactor().redact_object(
            {
                "available": True,
                "passed": passed,
                "checks": checks,
                "cases": results,
                "artifact_hash": fingerprint,
                "source_unchanged": data["source_unchanged"],
            }
        )
    except Exception:
        logger.exception("phase6.assess failed")
        raise
