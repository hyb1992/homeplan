"""pre-commit이 전달한 경로만 확인한다. 파일 내용은 출력하지 않는다."""

import sys
from pathlib import PurePath

bad = [
    name
    for name in sys.argv[1:]
    if PurePath(name).suffix.lower() in {".xlsx", ".xls", ".bak"}
    or PurePath(name).name in {"HANDOFF_CODEX.md", "VALIDATION.md", "scenarios.json", "units.json"}
    or ".local." in name
    or "backups" in PurePath(name).parts
]
if bad:
    print("커밋 금지 경로: " + ", ".join(bad))
    raise SystemExit(1)
