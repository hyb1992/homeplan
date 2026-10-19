"""파일 경계. 입력 백업·원자적 저장·규칙 로딩."""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from .models import Household
from .rules import RuleBook


def json_default(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    from decimal import Decimal

    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"JSON으로 바꿀 수 없는 형식: {type(value).__name__}")


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=json_default)


def read_json(path: Path) -> dict[str, Any]:
    from .repository import canonical_repository

    connection = canonical_repository(path)
    if connection:
        repo, key = connection
        stored = repo.get(key)
        return {**stored["household"], "_db_revision": stored["revision"]}
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("가구 JSON은 객체여야 합니다")
    return value


def load_household(path: Path) -> Household:
    return Household.model_validate(read_json(path))


def save_json(path: Path, data: dict[str, Any]) -> Path | None:
    from .repository import canonical_repository

    connection = canonical_repository(path)
    if connection:
        repo, key = connection
        expected = data.get("_db_revision", repo.get(key)["revision"])
        repo.save(key, data, expected)
        return repo.path
    Household.model_validate(data).resolved()
    payload = dumps(data) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if path.exists():
        backup_dir = path.parent / "backups"
        backup_dir.mkdir(exist_ok=True)
        backup = backup_dir / f"{path.name}.{datetime.now().strftime('%Y%m%dT%H%M%S%f')}.bak"
        backup.write_bytes(path.read_bytes())
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return backup


def default_rules_dir() -> Path:
    repo = Path(__file__).resolve().parents[2] / "data" / "rules"
    return repo if repo.is_dir() else Path(__file__).parent / "bundled_rules"


def load_rules(directory: Path | None = None) -> RuleBook:
    directory = directory or default_rules_dir()
    data: dict[str, Any] = {}
    for path in sorted(directory.glob("*.yaml")):
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"규칙은 객체여야 합니다: {path.name}")
        meta = value.get("meta", {})
        missing = {"source", "checked_at", "status"} - set(meta)
        if missing:
            raise ValueError(f"규칙 메타데이터 누락: {path.name}: {sorted(missing)}")
        data[path.stem] = value
    required = {
        "acquisition_tax",
        "brokerage",
        "registration",
        "childcare",
        "lending",
        "land_permit",
        "family_transfer",
    }
    if required - set(data):
        raise ValueError(f"필수 규칙 파일 누락: {sorted(required - set(data))}")
    return RuleBook(data)
