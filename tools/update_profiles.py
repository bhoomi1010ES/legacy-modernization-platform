with open("backend/app/core/config.py", "r", encoding="utf-8") as f:
    content = f.read()

old_snippet = """    return json.dumps({
        "Python": make_profile("python-v1"),
        "python-fastapi": make_profile("python-fastapi-v1"),
        "Python / FastAPI": make_profile("python-fastapi-v1"),
        "Django REST Framework": make_profile("django-drf-v1"),
        "TypeScript / NestJS": make_profile("typescript-nestjs-v1"),
        "Node / Express": make_profile("node-express-v1"),
    })"""

new_snippet = """    return json.dumps({
        "Python": make_profile("python-v1"),
        "python-fastapi": make_profile("python-fastapi-v1"),
        "Python / FastAPI": make_profile("python-fastapi-v1"),
        "FastAPI": make_profile("python-fastapi-v1"),
        "convert its backend into fastapi": make_profile("python-fastapi-v1"),
        "Django REST Framework": make_profile("django-drf-v1"),
        "TypeScript / NestJS": make_profile("typescript-nestjs-v1"),
        "Node / Express": make_profile("node-express-v1"),
        "Next.js": make_profile("typescript-nestjs-v1"),
        "Next.js (React)": make_profile("typescript-nestjs-v1"),
    })"""

if old_snippet in content:
    content = content.replace(old_snippet, new_snippet, 1)
    with open("backend/app/core/config.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("SUCCESS: Updated config.py")
else:
    print("NOT FOUND in config.py")
