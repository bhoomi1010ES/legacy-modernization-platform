with open("backend/app/models/__init__.py", "r", encoding="utf-8") as f:
    c = f.read()

c = c.replace("from app.models.artifact import Artifact", "from app.models.artifact import Artifact, ArtifactDependency")
c = c.replace('"Artifact",\n', '"Artifact",\n    "ArtifactDependency",\n')
c = c.replace('"Artifact",\r\n', '"Artifact",\r\n    "ArtifactDependency",\r\n')

with open("backend/app/models/__init__.py", "w", encoding="utf-8") as f:
    f.write(c)

print("Updated models/__init__.py with ArtifactDependency successfully")

