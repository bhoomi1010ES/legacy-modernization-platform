"""Remove the invalid content_hash parameter from create_artifact call."""
FILE = r"C:\Users\lenovo\Desktop\rebase\backend\tests\test_w08_planner_dag_and_scheduler.py"

with open(FILE, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Find and remove the line with content_hash="snap_hash_001"
new_lines = []
for line in lines:
    if 'content_hash="snap_hash_001",' in line:
        continue  # skip this line
    new_lines.append(line)

with open(FILE, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("Removed content_hash='snap_hash_001' line")

