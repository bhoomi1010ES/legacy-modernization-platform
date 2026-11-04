from pathlib import Path

p = Path("backend/tests/test_w01_security.py")
text = p.read_text(encoding="utf-8")

new_test = '''def test_w01_1_production_configuration_safeguards(monkeypatch):
    """Proves production configuration strictly rejects insecure default keys and wildcards."""
    monkeypatch.setenv("ENVIRONMENT", "production")

    from app.core.config import Settings

    # 1. Reject default dev secret key in production
    with pytest.raises(ValueError) as exc:
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="phase-0-development-secret-key-change-in-production-min32bytes!",
        )
    assert "insecure secret_key detected for production" in str(exc.value).lower()

    # 2. Reject wildcard allowed hosts in production
    with pytest.raises(ValueError) as exc2:
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="a-sufficiently-long-and-cryptographically-secure-production-key-here!",
            ALLOWED_HOSTS=["*"],
        )
    assert "allowed_hosts cannot be empty or wildcard in production" in str(exc2.value).lower()

    # 3. Enforce secure cookies in production
    prod_settings = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="a-sufficiently-long-and-cryptographically-secure-production-key-here!",
        ALLOWED_HOSTS=["app.rebase.internal"],
        SESSION_COOKIE_SECURE=False,
    )
    assert prod_settings.SESSION_COOKIE_SECURE is True


'''

target = '# W01.2 — Public Registration Role Lockdown & Admin Assignment'
if 'test_w01_1_production_configuration_safeguards' not in text:
    text = text.replace(target, new_test + target)
    p.write_text(text, encoding="utf-8")
    print("Added production configuration safeguards test to test_w01_security.py")

