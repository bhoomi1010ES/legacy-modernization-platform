"""Applies W01 security remediation across backend services and routes."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent

def patch_job_service():
    p = ROOT / "backend" / "app" / "services" / "job_service.py"
    text = p.read_text(encoding="utf-8")
    assert 'role_id="ADMIN"' in text, "Target ADMIN role not found in job_service.py"
    
    text = text.replace(
        '        # Grant owner membership with ADMIN role\n        membership = JobMembership(\n            job_id=job_id,\n            user_id=user.user_id,\n            role_id="ADMIN",\n        )',
        '        # Grant owner membership with least-privilege DEVELOPER role (SEC-03)\n        membership = JobMembership(\n            job_id=job_id,\n            user_id=user.user_id,\n            role_id="DEVELOPER",\n        )'
    )
    # Also handle CRLF if present
    text = text.replace(
        '        # Grant owner membership with ADMIN role\r\n        membership = JobMembership(\r\n            job_id=job_id,\r\n            user_id=user.user_id,\r\n            role_id="ADMIN",\r\n        )',
        '        # Grant owner membership with least-privilege DEVELOPER role (SEC-03)\r\n        membership = JobMembership(\r\n            job_id=job_id,\r\n            user_id=user.user_id,\r\n            role_id="DEVELOPER",\r\n        )'
    )
    p.write_text(text, encoding="utf-8")
    print("Patched job_service.py (SEC-03)")

def patch_gate_service():
    p = ROOT / "backend" / "app" / "services" / "gate_service.py"
    text = p.read_text(encoding="utf-8")
    
    # Add ForbiddenException, ErrorDetail import
    if "ForbiddenException" not in text:
        text = text.replace(
            "from app.core.errors import ConflictException, NotFoundException",
            "from app.core.errors import ConflictException, NotFoundException, ForbiddenException, ErrorDetail"
        )
    
    # Add creator check in decide
    old_target = "        if gate.status != \"PENDING\":\n            raise ConflictException(f\"Gate already has terminal status {gate.status}.\")"
    new_target = """        if not job:
            raise NotFoundException("Job", str(gate.job_id))

        # Separation of duties: Job creator cannot approve or reject gates for their own job (W01.6)
        if job.owner_user_id and job.owner_user_id == actor_id:
            raise ForbiddenException(
                message="Separation of duties violation: job creator cannot approve or reject gates for their own job.",
                details=[ErrorDetail(field="actor_id", issue="Job creator cannot act as gate reviewer")],
            )

        if gate.status != "PENDING":
            raise ConflictException(f"Gate already has terminal status {gate.status}.")"""

    if "Separation of duties violation: job creator cannot approve" not in text:
        if old_target in text:
            text = text.replace(old_target, new_target)
        else:
            old_crlf = old_target.replace("\n", "\r\n")
            new_crlf = new_target.replace("\n", "\r\n")
            text = text.replace(old_crlf, new_crlf)
            
    p.write_text(text, encoding="utf-8")
    print("Patched gate_service.py (W01.6)")

def patch_state_machine():
    p = ROOT / "backend" / "app" / "domain" / "state_machine.py"
    text = p.read_text(encoding="utf-8")
    
    old_target = """        # Rule 2: Approver must possess an authorized role
        if actor_role not in cls.AUTHORIZED_APPROVER_ROLES:
            raise ForbiddenException(
                message=f"Role '{actor_role}' is not authorized to decide approval gates. Requires REVIEWER or ADMIN."
            )"""

    new_target = """        # Rule 2: Approver must possess an authorized role and permission
        if actor_role not in cls.AUTHORIZED_APPROVER_ROLES:
            raise ForbiddenException(
                message=f"Role '{actor_role}' is not authorized to decide approval gates. Requires REVIEWER or ADMIN."
            )
        if not RBACPolicy.has_permission(actor_role, f"gate:approve_{gate_type.value.lower()}"):
            raise ForbiddenException(
                message=f"Role '{actor_role}' lacks required permission 'gate:approve_{gate_type.value.lower()}'."
            )"""

    if "lacks required permission 'gate:approve_" not in text:
        if old_target in text:
            text = text.replace(old_target, new_target)
        else:
            old_crlf = old_target.replace("\n", "\r\n")
            new_crlf = new_target.replace("\n", "\r\n")
            text = text.replace(old_crlf, new_crlf)

    p.write_text(text, encoding="utf-8")
    print("Patched state_machine.py (W01.6)")

def patch_git_adapter():
    p = ROOT / "backend" / "app" / "services" / "git_adapter.py"
    text = p.read_text(encoding="utf-8")
    
    old_target = """        # SSRF Protection: Resolve hostname to IP and check against forbidden ranges
        if not self.allow_local_repos_for_test:
            try:
                ip_addresses = socket.getaddrinfo(hostname, None)
                for addr in ip_addresses:
                    ip_str = addr[4][0]
                    ip_obj = ipaddress.ip_address(ip_str)
                    # Handle IPv4-mapped IPv6 addresses (e.g. ::ffff:127.0.0.1)
                    if ip_obj.version == 6 and ip_obj.ipv4_mapped:
                        ip_obj = ip_obj.ipv4_mapped
                    if (
                        ip_obj.is_loopback
                        or ip_obj.is_private
                        or ip_obj.is_link_local
                        or ip_obj.is_unspecified
                        or ip_obj.is_multicast
                        or ip_obj.is_reserved
                    ):
                        raise GitSecurityException(
                            f"SSRF violation: Host '{hostname}' resolves to private/prohibited IP '{ip_str}'."
                        )
            except socket.gaierror:
                raise GitSecurityException(f"Unable to resolve hostname: '{hostname}'.")"""

    new_target = """        # SSRF Protection: Loopback, private IP, link-local, and cloud metadata defense
        if hostname.lower() in ("localhost", "localhost.localdomain"):
            raise GitSecurityException(
                f"SSRF violation: Host '{hostname}' is a prohibited loopback target."
            )

        try:
            ip_obj = ipaddress.ip_address(hostname)
            if ip_obj.version == 6 and ip_obj.ipv4_mapped:
                ip_obj = ip_obj.ipv4_mapped
            if (
                ip_obj.is_loopback
                or ip_obj.is_private
                or ip_obj.is_link_local
                or ip_obj.is_unspecified
                or ip_obj.is_multicast
                or ip_obj.is_reserved
            ):
                raise GitSecurityException(
                    f"SSRF violation: Host '{hostname}' resolves to private/prohibited IP '{hostname}'."
                )
        except ValueError:
            # Domain name: resolve and inspect all target addresses
            if not self.allow_local_repos_for_test:
                try:
                    ip_addresses = socket.getaddrinfo(hostname, None)
                    for addr in ip_addresses:
                        ip_str = addr[4][0]
                        ip_obj = ipaddress.ip_address(ip_str)
                        if ip_obj.version == 6 and ip_obj.ipv4_mapped:
                            ip_obj = ip_obj.ipv4_mapped
                        if (
                            ip_obj.is_loopback
                            or ip_obj.is_private
                            or ip_obj.is_link_local
                            or ip_obj.is_unspecified
                            or ip_obj.is_multicast
                            or ip_obj.is_reserved
                        ):
                            raise GitSecurityException(
                                f"SSRF violation: Host '{hostname}' resolves to private/prohibited IP '{ip_str}'."
                            )
                except socket.gaierror:
                    raise GitSecurityException(f"Unable to resolve hostname: '{hostname}'.")"""

    if "Loopback, private IP, link-local, and cloud metadata defense" not in text:
        if old_target in text:
            text = text.replace(old_target, new_target)
        else:
            old_crlf = old_target.replace("\n", "\r\n")
            new_crlf = new_target.replace("\n", "\r\n")
            text = text.replace(old_crlf, new_crlf)

    p.write_text(text, encoding="utf-8")
    print("Patched git_adapter.py (SSRF Hardening)")

def patch_main():
    p = ROOT / "backend" / "app" / "main.py"
    text = p.read_text(encoding="utf-8")
    
    # Import TrustedHostMiddleware
    if "TrustedHostMiddleware" not in text:
        text = text.replace(
            "from fastapi.middleware.cors import CORSMiddleware",
            "from fastapi.middleware.cors import CORSMiddleware\nfrom starlette.middleware.trustedhost import TrustedHostMiddleware"
        )
    
    # Add TrustedHostMiddleware after CORS
    old_cors = """    # CORS configuration for browser clients
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )"""

    new_cors_and_host = """    # CORS configuration for browser clients
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # SEC-05 / SEC-08: Host header protection
    allowed_hosts = list(settings.ALLOWED_HOSTS or ["localhost", "127.0.0.1", "testserver"])
    if settings.ENVIRONMENT == "production":
        allowed_hosts = [h for h in allowed_hosts if h != "*"]
        if not allowed_hosts:
            allowed_hosts = ["localhost", "127.0.0.1"]
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=allowed_hosts,
    )"""

    if "TrustedHostMiddleware," not in text:
        if old_cors in text:
            text = text.replace(old_cors, new_cors_and_host)
        else:
            old_crlf = old_cors.replace("\n", "\r\n")
            new_crlf = new_cors_and_host.replace("\n", "\r\n")
            text = text.replace(old_crlf, new_crlf)

    # Patch CSRF substring match (SEC-08)
    old_csrf = """                    allowed = set(settings.CORS_ALLOWED_ORIGINS)
                    host = request.headers.get("host")
                    is_allowed = (
                        check_val in allowed
                        or (host and host in check_val)
                        or any(check_val == o for o in settings.CORS_ALLOWED_ORIGINS)
                    )"""

    new_csrf = """                    allowed = set(settings.CORS_ALLOWED_ORIGINS)
                    host = request.headers.get("host")
                    # SEC-08: Exact origin match or exact host match (no loose substring search)
                    is_allowed = check_val in allowed
                    if not is_allowed and host:
                        from urllib.parse import urlparse
                        parsed_val = urlparse(check_val)
                        if parsed_val.netloc == host or parsed_val.hostname == host:
                            is_allowed = True"""

    if "Exact origin match or exact host match" not in text:
        if old_csrf in text:
            text = text.replace(old_csrf, new_csrf)
        else:
            old_crlf = old_csrf.replace("\n", "\r\n")
            new_crlf = new_csrf.replace("\n", "\r\n")
            text = text.replace(old_crlf, new_crlf)

    p.write_text(text, encoding="utf-8")
    print("Patched main.py (SEC-05 / SEC-08)")

def patch_config():
    p = ROOT / "backend" / "app" / "core" / "config.py"
    text = p.read_text(encoding="utf-8")

    # Add validators for production cookie and host safety
    target_pos = '        model_config = SettingsConfigDict('
    validator_code = '''        @field_validator("SESSION_COOKIE_SECURE", mode="before")
        @classmethod
        def validate_cookie_secure(cls, v: Any) -> bool:
            env = os.getenv("ENVIRONMENT", "development").lower()
            if env == "production":
                return True
            if isinstance(v, bool):
                return v
            if isinstance(v, str):
                return v.strip().lower() in ("true", "1", "t", "yes", "y")
            return bool(v)

        @field_validator("ALLOWED_HOSTS")
        @classmethod
        def validate_allowed_hosts(cls, v: Any) -> List[str]:
            hosts = v if isinstance(v, list) else [str(v)]
            env = os.getenv("ENVIRONMENT", "development").lower()
            if env == "production":
                hosts = [h for h in hosts if h != "*"]
                if not hosts:
                    raise ValueError("ALLOWED_HOSTS cannot be empty or wildcard in production.")
            return hosts

'''
    if "validate_cookie_secure" not in text:
        text = text.replace(target_pos, validator_code + target_pos)

    p.write_text(text, encoding="utf-8")
    print("Patched config.py (SEC-05)")

def patch_jobs_endpoints():
    p = ROOT / "backend" / "app" / "api" / "v1" / "jobs.py"
    text = p.read_text(encoding="utf-8")

    # 1. Require get_current_user on detect_stack
    text = text.replace(
        "async def detect_stack(\n    payload: StackDetectionRequest,\n    request: Request,\n    user: Optional[User] = Depends(get_optional_user),",
        "async def detect_stack(\n    payload: StackDetectionRequest,\n    request: Request,\n    user: User = Depends(get_current_user),"
    )
    text = text.replace(
        "async def detect_stack(\r\n    payload: StackDetectionRequest,\r\n    request: Request,\r\n    user: Optional[User] = Depends(get_optional_user),",
        "async def detect_stack(\r\n    payload: StackDetectionRequest,\r\n    request: Request,\r\n    user: User = Depends(get_current_user),"
    )

    # 2. Require get_current_user on detect_stack_local
    text = text.replace(
        "async def detect_stack_local(\n    bundle: UploadFile = File(..., description=\"Zipped local project source bundle\"),\n    source_name: str = Form(\"local-project\", description=\"Display name of local folder\"),\n    job_id: Optional[str] = Form(None, description=\"Optional job ID\"),\n    request: Request = None,\n    user: Optional[User] = Depends(get_optional_user),",
        "async def detect_stack_local(\n    bundle: UploadFile = File(..., description=\"Zipped local project source bundle\"),\n    source_name: str = Form(\"local-project\", description=\"Display name of local folder\"),\n    job_id: Optional[str] = Form(None, description=\"Optional job ID\"),\n    request: Request = None,\n    user: User = Depends(get_current_user),"
    )
    text = text.replace(
        "async def detect_stack_local(\r\n    bundle: UploadFile = File(..., description=\"Zipped local project source bundle\"),\r\n    source_name: str = Form(\"local-project\", description=\"Display name of local folder\"),\r\n    job_id: Optional[str] = Form(None, description=\"Optional job ID\"),\r\n    request: Request = None,\r\n    user: Optional[User] = Depends(get_optional_user),",
        "async def detect_stack_local(\r\n    bundle: UploadFile = File(..., description=\"Zipped local project source bundle\"),\r\n    source_name: str = Form(\"local-project\", description=\"Display name of local folder\"),\r\n    job_id: Optional[str] = Form(None, description=\"Optional job ID\"),\r\n    request: Request = None,\r\n    user: User = Depends(get_current_user),"
    )

    # 3. Secure path inspection logic in detect_stack
    old_detection_logic = """    raw_path = payload.source_repository.strip()
    is_local_request = (payload.source_type == "local") or raw_path.startswith("local://")
    if not is_local_request:
        try:
            p = Path(raw_path)
            if p.is_absolute() and (p.exists() or not (raw_path.startswith("http://") or raw_path.startswith("https://") or raw_path.startswith("git@"))):
                is_local_request = True
        except Exception:
            pass

    if is_local_request:
        clean_path_str = raw_path.removeprefix("local://")
        local_dir = Path(clean_path_str).resolve()
        if not local_dir.exists():
            raise ValidationException(
                f"Local directory path '{clean_path_str}' was not found on this machine.",
                details=[ErrorDetail(field="source_repository", issue="Local directory does not exist")],
            )
        if local_dir.is_file() and clean_path_str.lower().endswith(".zip"):
            from app.services.local_source_adapter import LocalSourceAdapter
            adapter = LocalSourceAdapter()
            staging_dir, metadata = adapter.stage_preview_bundle(
                archive_path=local_dir,
                source_name=local_dir.stem,
                user_id=str(user.user_id) if user else "local-operator",
            )
            detected = StackDetector.detect_stack_from_workspace(
                workspace_path=staging_dir,
                source_name=local_dir.stem,
                source_revision="LOCAL",
                preview_snapshot_id=metadata.snapshot_id,
                snapshot_fingerprint=metadata.canonical_fingerprint,
                extra_warnings=metadata.warnings,
                is_complete=metadata.is_complete,
            )
            detected.source_repository = str(local_dir)
            detected.source_type = "local"
        elif not local_dir.is_dir():
            raise ValidationException(
                f"Path '{clean_path_str}' is neither a directory nor a .zip archive.",
                details=[ErrorDetail(field="source_repository", issue="Target must be a directory or .zip archive")],
            )
        else:
            from app.services.local_source_adapter import LocalSourceAdapter
            fingerprint = LocalSourceAdapter.calculate_canonical_fingerprint(local_dir)
            detected = StackDetector.detect_stack_from_workspace(
                workspace_path=local_dir,
                source_name=local_dir.name,
                source_revision="LOCAL",
                snapshot_fingerprint=fingerprint,
            )
            detected.source_repository = str(local_dir)
            detected.source_type = "local"
    else:
        detected = StackDetector.detect_stack(
            source_repository=payload.source_repository,
            source_revision=payload.source_revision or "main",
            access_token=payload.access_token,
        )"""

    new_detection_logic = """    raw_path = (payload.source_repository or "").strip()
    if not raw_path:
        raise ValidationException(
            "Repository source cannot be empty.",
            details=[ErrorDetail(field="source_repository", issue="Repository path or URL is required.")],
        )

    # Validate job authorization if job_id is provided
    if payload.job_id:
        from app.models.job import Job, JobMembership
        from sqlalchemy import select
        import uuid
        try:
            clean_job_id = uuid.UUID(str(payload.job_id))
            job_res = await db.execute(select(Job).where(Job.job_id == clean_job_id))
            target_job = job_res.scalar_one_or_none()
            if not target_job:
                raise NotFoundException("Job", str(payload.job_id))
            if user.role != "SUPER_ADMIN" and target_job.owner_user_id != user.user_id:
                mem_res = await db.execute(
                    select(JobMembership).where(
                        JobMembership.job_id == target_job.job_id,
                        JobMembership.user_id == user.user_id,
                    )
                )
                if not mem_res.scalar_one_or_none():
                    raise ForbiddenException("User is not authorized for this job.")
        except (ValueError, TypeError):
            raise ValidationException(
                "Invalid job_id format.",
                details=[ErrorDetail(field="job_id", issue="Must be a valid UUID")],
            )

    is_local_request = (payload.source_type == "local") or raw_path.startswith("local://")
    if not is_local_request:
        try:
            p = Path(raw_path)
            if p.is_absolute() and not (raw_path.startswith("http://") or raw_path.startswith("https://") or raw_path.startswith("git@")):
                is_local_request = True
        except Exception:
            pass

    if is_local_request:
        if settings.ENVIRONMENT == "production":
            raise ForbiddenException(
                "Local filesystem repository scanning is disabled in production.",
                details=[ErrorDetail(field="source_repository", issue="Local scanning prohibited in production")],
            )
        clean_path_str = raw_path.removeprefix("local://")
        local_dir = Path(clean_path_str).resolve()

        resolved_lower = str(local_dir).lower()
        blocked_system_prefixes = (
            "c:\\\\windows", "c:\\\\program files", "c:\\\\program files (x86)",
            "/etc", "/var", "/usr", "/bin", "/sbin", "/root", "/proc", "/sys"
        )
        if any(resolved_lower.startswith(prefix) for prefix in blocked_system_prefixes) or local_dir.parent == local_dir:
            raise ForbiddenException(
                f"Access to sensitive system path '{clean_path_str}' is denied.",
                details=[ErrorDetail(field="source_repository", issue="System paths are forbidden")],
            )

        if not local_dir.exists():
            raise ValidationException(
                f"Local directory path '{clean_path_str}' was not found on this machine.",
                details=[ErrorDetail(field="source_repository", issue="Local directory does not exist")],
            )
        if local_dir.is_file() and clean_path_str.lower().endswith(".zip"):
            from app.services.local_source_adapter import LocalSourceAdapter
            adapter = LocalSourceAdapter()
            staging_dir, metadata = adapter.stage_preview_bundle(
                archive_path=local_dir,
                source_name=local_dir.stem,
                user_id=str(user.user_id),
            )
            detected = StackDetector.detect_stack_from_workspace(
                workspace_path=staging_dir,
                source_name=local_dir.stem,
                source_revision="LOCAL",
                preview_snapshot_id=metadata.snapshot_id,
                snapshot_fingerprint=metadata.canonical_fingerprint,
                extra_warnings=metadata.warnings,
                is_complete=metadata.is_complete,
            )
            detected.source_repository = str(local_dir)
            detected.source_type = "local"
        elif not local_dir.is_dir():
            raise ValidationException(
                f"Path '{clean_path_str}' is neither a directory nor a .zip archive.",
                details=[ErrorDetail(field="source_repository", issue="Target must be a directory or .zip archive")],
            )
        else:
            from app.services.local_source_adapter import LocalSourceAdapter
            fingerprint = LocalSourceAdapter.calculate_canonical_fingerprint(local_dir)
            detected = StackDetector.detect_stack_from_workspace(
                workspace_path=local_dir,
                source_name=local_dir.name,
                source_revision="LOCAL",
                snapshot_fingerprint=fingerprint,
            )
            detected.source_repository = str(local_dir)
            detected.source_type = "local"
    else:
        # Enforce remote repository validation against SSRF and command injection
        git_adapter = ControlledGitAdapter()
        git_adapter.validate_source_url(raw_path)

        detected = StackDetector.detect_stack(
            source_repository=payload.source_repository,
            source_revision=payload.source_revision or "main",
            access_token=payload.access_token,
            git_adapter=git_adapter,
        )"""

    if "Enforce remote repository validation against SSRF" not in text:
        if old_detection_logic in text:
            text = text.replace(old_detection_logic, new_detection_logic)
        else:
            old_crlf = old_detection_logic.replace("\n", "\r\n")
            new_crlf = new_detection_logic.replace("\n", "\r\n")
            text = text.replace(old_crlf, new_crlf)

    p.write_text(text, encoding="utf-8")
    print("Patched jobs.py (SEC-04)")

if __name__ == "__main__":
    patch_job_service()
    patch_gate_service()
    patch_state_machine()
    patch_git_adapter()
    patch_main()
    patch_config()
    patch_jobs_endpoints()
    print("All W01 patches applied successfully!")

