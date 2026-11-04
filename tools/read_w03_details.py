from pathlib import Path

content = Path("docs/remediation/w00/REMEDIATION_EVIDENCE_LEDGER.md").read_text(encoding="utf-8")
sections = content.split("### `")

for sec in sections[1:]:
    header = sec.split("`")[0]
    if header in ("DATA-02", "DATA-03", "DATA-04", "DATA-05", "DATA-06"):
        print("=" * 80)
        print(f"### `{header}`")
        print(sec[:1500])

