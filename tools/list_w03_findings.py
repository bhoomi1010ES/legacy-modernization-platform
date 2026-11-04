from pathlib import Path
import re

content = Path("docs/remediation/w00/REMEDIATION_EVIDENCE_LEDGER.md").read_text(encoding="utf-8")
sections = content.split("### `")

print("Findings targeting W03:")
for sec in sections[1:]:
    header = sec.split("`")[0]
    lines = sec.splitlines()
    title = lines[0].split("`:")[-1].strip() if "`:" in lines[0] else lines[0]
    target = ""
    status = ""
    for line in lines:
        if "Workstream Target:" in line:
            target = line.split("Workstream Target:")[-1].strip()
        if "Current Status:" in line:
            status = line.split("Current Status:")[-1].strip()
    if "W03" in target:
        print(f"[{header}] {title} | Target: {target} | Status: {status}")

