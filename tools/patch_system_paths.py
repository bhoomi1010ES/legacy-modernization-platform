from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 1. Update jobs.py path check
jobs_path = ROOT / "backend" / "app" / "api" / "v1" / "jobs.py"
jobs_text = jobs_path.read_text(encoding="utf-8")

old_block = """            resolved_lower = str(local_dir).lower()
            blocked_system_prefixes = (
                "c:\\\\windows", "c:\\\\program files", "c:\\\\program files (x86)",
                "/etc", "/var", "/usr", "/bin", "/sbin", "/root", "/proc", "/sys"
            )
            if any(resolved_lower.startswith(prefix) for prefix in blocked_system_prefixes) or local_dir.parent == local_dir:
                raise ForbiddenException(
                    f"Access to sensitive system path '{clean_path_str}' is denied.",
                    details=[ErrorDetail(field="source_repository", issue="System paths are forbidden")],
                )"""

new_block = """            path_normalized = clean_path_str.lower().replace("\\\\", "/")
            resolved_normalized = str(local_dir).lower().replace("\\\\", "/")
            blocked_system_prefixes = (
                "c:/windows", "c:/program files", "c:/program files (x86)",
                "/etc", "/var", "/usr", "/bin", "/sbin", "/root", "/proc", "/sys",
                "c:/etc", "c:/var", "c:/usr", "c:/bin", "c:/root"
            )
            if (
                any(path_normalized.startswith(prefix) for prefix in blocked_system_prefixes)
                or any(resolved_normalized.startswith(prefix) for prefix in blocked_system_prefixes)
                or local_dir.parent == local_dir
            ):
                raise ForbiddenException(
                    f"Access to sensitive system path '{clean_path_str}' is denied.",
                    details=[ErrorDetail(field="source_repository", issue="System paths are forbidden")],
                )"""

if old_block in jobs_text:
    jobs_text = jobs_text.replace(old_block, new_block)
    jobs_path.write_text(jobs_text, encoding="utf-8")
    print("Updated system path blocking in jobs.py")

# 2. Update test_w01_security.py reviewer user creation
test_path = ROOT / "backend" / "tests" / "test_w01_security.py"
test_text = test_path.read_text(encoding="utf-8")

old_reviewer_creation = """    # 4. Provision an independent REVIEWER user
    reviewer_email = f"reviewer_{uuid.uuid4().hex[:8]}@acme.corp"
    async with AsyncSessionLocal() as session:
        reviewer_user = User(
            email=reviewer_email,
            full_name="Independent Reviewer",
            password_hash=hash_password("ReviewerPass123!"),
            role="REVIEWER",
            status="ACTIVE",
        )
        session.add(reviewer_user)
        # Grant reviewer membership on this job
        mem = JobMembership(
            job_id=job_id,
            user_id=reviewer_user.user_id,
            role_id="REVIEWER",
        )
        session.add(mem)
        await session.commit()"""

new_reviewer_creation = """    # 4. Provision an independent REVIEWER user
    reviewer_email = f"reviewer_{uuid.uuid4().hex[:8]}@acme.corp"
    reviewer_user_id = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        reviewer_user = User(
            user_id=reviewer_user_id,
            email=reviewer_email,
            full_name="Independent Reviewer",
            password_hash=hash_password("ReviewerPass123!"),
            role="REVIEWER",
            status="ACTIVE",
        )
        session.add(reviewer_user)
        # Grant reviewer membership on this job
        mem = JobMembership(
            job_id=job_id,
            user_id=reviewer_user_id,
            role_id="REVIEWER",
        )
        session.add(mem)
        await session.commit()"""

if old_reviewer_creation in test_text:
    test_text = test_text.replace(old_reviewer_creation, new_reviewer_creation)
    test_path.write_text(test_text, encoding="utf-8")
    print("Updated test_w01_security.py reviewer creation with explicit UUID")

