with open("LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, l in enumerate(lines):
    if "## 8. W05" in l:
        for j in range(i, min(len(lines), i + 35)):
            print(f"{j+1}: {lines[j].strip()}")
        break

