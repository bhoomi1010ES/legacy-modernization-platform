"""Add content_hash back to RepositorySnapshotModel constructor."""
FILE = r"C:\Users\lenovo\Desktop\rebase\backend\tests\test_w08_planner_dag_and_scheduler.py"

with open(FILE, "r", encoding="utf-8") as f:
    content = f.read()

old = '''            commit_sha="abc123456789",
            inventory_hash="inv_hash_001",'''

new = '''            commit_sha="abc123456789",
            content_hash="snap_hash_001",
            inventory_hash="inv_hash_001",'''

assert old in content, "Could not find RepositorySnapshotModel pattern"
content = content.replace(old, new, 1)

with open(FILE, "w", encoding="utf-8") as f:
    f.write(content)

print("Added content_hash back to RepositorySnapshotModel constructor")

