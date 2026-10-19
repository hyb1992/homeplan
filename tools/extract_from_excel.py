"""호환 실행기: uv run python tools/extract_from_excel.py 원본.xlsx 출력.local.json."""

import sys
from pathlib import Path

from homeplan.cli import today_korea
from homeplan.importer import import_excel

if __name__ == "__main__":
    _, backup = import_excel(Path(sys.argv[1]), Path(sys.argv[2]), today_korea())
    print(f"저장 완료. 백업: {backup or '신규 파일'}")
