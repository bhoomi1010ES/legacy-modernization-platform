"""Versioned target-stack profiles frozen into independent verification runs."""

import json
import re

from app.core.config import settings
from app.services.phase5_engine import digest
from app.services.sandbox_protocol import approved_command, validate_check_profile


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate key in target verification profile")
        result[key] = value
    return result


def _profile_map():
    profiles = json.loads(settings.PHASE6_TARGET_PROFILES_JSON, object_pairs_hook=_unique_object)
    if not isinstance(profiles, dict):
        raise ValueError("Target verification profiles must be a JSON object")
    return profiles


def normalize_target(target_stack):
    if not isinstance(target_stack, str) or not target_stack.strip():
        raise ValueError("Job target stack is required for target-specific verification")
    return " ".join(target_stack.casefold().split())


def get_profile(target_stack):
    """Return the versioned target profile matching the job's target stack.
    Supports exact match or canonical framework/runtime keyword matching."""
    target = normalize_target(target_stack)
    profiles = _profile_map()
    matches = [value for name, value in profiles.items() if normalize_target(name) == target]
    if len(matches) == 1:
        profile = matches[0]
    else:
        target_tokens = set(re.findall(r"[a-z0-9]+", target))
        scored = []
        for name, value in profiles.items():
            name_norm = normalize_target(name)
            name_tokens = set(re.findall(r"[a-z0-9]+", name_norm))
            if name_tokens and name_tokens.issubset(target_tokens):
                score = len(name_tokens) * 100 + len(name_norm)
                scored.append((score, value))
            elif any(t in target_tokens for t in name_tokens if len(t) > 3):
                overlap = len([t for t in name_tokens if t in target_tokens and len(t) > 3])
                score = overlap * 50 + len(name_norm)
                scored.append((score, value))
        if scored:
            scored.sort(key=lambda s: s[0], reverse=True)
            profile = scored[0][1]
        else:
            raise ValueError(f"No unique versioned verification profile is configured for target stack '{target_stack}'")
    required = {"version", "image", "runtime", "timeout", "adapter", "checks", "system_checks"}
    if not isinstance(profile, dict) or set(profile) != required:
        raise ValueError("Target verification profile has missing or unexpected fields")
    if not isinstance(profile["version"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,49}", profile["version"]):
        raise ValueError("Target verification profile version is invalid")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(profile["image"])):
        raise ValueError("Target verification profile must pin an immutable image digest")
    if profile["runtime"] not in {"docker-rootless", "gvisor-rootless", "e2b-microvm"} or type(profile["timeout"]) is not int or not 1 <= profile["timeout"] <= 600:
        raise ValueError("Target verification runtime or deadline is invalid")
    if not approved_command(profile["adapter"], adapter=True):
        raise ValueError("Target verification adapter is not approved")
    checks = profile["checks"]
    if not isinstance(checks, list) or not validate_check_profile(checks, system=False, schema_required=any(c.get("category") == "schema" for c in checks)):
        raise ValueError("Target module verification profile is incomplete or unsafe")
    system_checks = profile["system_checks"]
    if not isinstance(system_checks, list) or not validate_check_profile(system_checks, system=True, schema_required=any(c.get("category") == "schema" for c in system_checks)):
        raise ValueError("Target full-system verification profile is incomplete or unsafe")
    return {**profile, "profile_digest": digest(profile), "target_key": target}


def available_profiles():
    """Validate and return configured target names, for truthful readiness reporting."""
    result = []
    for target in _profile_map():
        profile = get_profile(target)
        result.append({"target": target, "version": profile["version"], "image": profile["image"]})
    return result
