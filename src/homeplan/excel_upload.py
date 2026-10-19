"""엑셀 파일의 읽기 전용 가져오기 미리보기. 저장은 기존 계획 API가 담당한다."""

import base64
import binascii
import copy
import tempfile
import zipfile
from collections.abc import Callable
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import ParseError

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .repository import clean_household

MAX_FILE_BYTES = 10 * 1024 * 1024


class ExcelPreviewInput(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content: str = Field(max_length=(MAX_FILE_BYTES + 2) // 3 * 4)
    household: dict[str, Any] | None = None
    refresh_imported: bool = False


def preview_excel(payload: ExcelPreviewInput, today: date) -> dict[str, Any]:
    from openpyxl.utils.exceptions import InvalidFileException

    from .importer import extract_excel, merge_import

    filename = payload.filename.replace("\\", "/").rsplit("/", 1)[-1]
    if Path(filename).suffix.lower() != ".xlsx":
        raise ValueError("매수계획 v18 형식의 .xlsx 파일을 선택하세요.")
    try:
        content = base64.b64decode(payload.content, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("엑셀 파일 내용을 읽지 못했습니다. 다시 선택하세요.") from error
    if not content or len(content) > MAX_FILE_BYTES:
        raise ValueError("엑셀 파일은 10MB 이하로 선택하세요.")
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 80 * 1024 * 1024:
                raise ValueError("압축을 푼 엑셀 크기가 너무 큽니다.")
        with tempfile.TemporaryDirectory(prefix="homeplan-import-") as folder:
            source = Path(folder) / "import.xlsx"
            source.write_bytes(content)
            incoming = extract_excel(source, today)
    except (zipfile.BadZipFile, InvalidFileException, ParseError, KeyError) as error:
        raise ValueError(
            "지원하는 매수계획 엑셀이 아닙니다. 기본설정·조건별비교·월별가계흐름·"
            "우리자금·아파트매물·결과요약 시트가 있는 v18 파일을 선택하세요."
        ) from error
    incoming["_source"] = filename
    # 서버의 임시 경로는 보관하지 않고 파일 이름만 출처로 남긴다.
    candidate = merge_import(
        payload.household or {}, incoming, refresh_imported=payload.refresh_imported
    )
    candidate = clean_household(candidate)
    if payload.household:
        # Track only changes made by this import; later GUI edits still become app-owned.
        baseline = copy.deepcopy(payload.household.get("_excel_import_baseline", {}))
        settings = baseline.setdefault("settings", {})
        for key, value in candidate["settings"].items():
            if value != payload.household.get("settings", {}).get(key):
                settings[key] = value
        for section in ("fund_events", "parent_support", "listings"):
            previous = {row.get("id"): row for row in payload.household.get(section, [])}
            rows = baseline.setdefault(section, {})
            for row in candidate[section]:
                if row.get("origin") == "excel" and row != previous.get(row.get("id")):
                    rows[row["id"]] = copy.deepcopy(row)
        candidate["_excel_import_baseline"] = baseline
    return {
        "household": candidate,
        "filename": filename,
        "warnings": list(dict.fromkeys(candidate.get("_import_warnings", [])))
        + (
            ["일부 설정이 엑셀에 없어 기본값을 사용합니다."]
            if incoming.get("_missing_labels")
            else []
        ),
        "counts": {
            key: len(candidate.get(key, []))
            for key in ("fund_events", "parent_support", "listings")
        },
    }


def install_excel_routes(app: FastAPI, today: Callable[[], date]) -> None:
    @app.post("/api/import-excel/preview")
    def preview(payload: ExcelPreviewInput) -> dict[str, Any]:
        return preview_excel(payload, today())
