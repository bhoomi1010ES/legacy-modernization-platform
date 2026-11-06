from app.services.verification_profiles import get_profile

for t in ["Python", "FastAPI", "python-fastapi", "convert its backend into fastapi", "migrate to django rest framework"]:
    try:
        p = get_profile(t)
        print(f"Target '{t}' -> version '{p['version']}'")
    except Exception as e:
        print(f"Target '{t}' -> ERROR: {e}")

