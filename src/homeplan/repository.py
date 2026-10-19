"""앱 기준 저장소. 최초 JSON 이관, revision 검사, 변경 전 버전 보관."""

import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .models import Household


class RevisionConflict(ValueError):
    pass


def timestamp() -> str:
    return datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds")


def clean_household(data: dict[str, Any]) -> dict[str, Any]:
    payload = dict(data)
    payload.pop("_db_revision", None)
    payload.pop("calculation_override_keys", None)
    model = Household.model_validate(payload)
    model.resolved()
    return model.model_dump(mode="json")


class Repository:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS households (
                    id TEXT PRIMARY KEY, label TEXT NOT NULL, payload TEXT NOT NULL,
                    revision INTEGER NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS household_versions (
                    household_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    payload TEXT NOT NULL, saved_at TEXT NOT NULL,
                    PRIMARY KEY (household_id, revision)
                );
            """)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def seed(self, key: str, label: str, data: dict[str, Any]) -> None:
        payload = json.dumps(clean_household(data), ensure_ascii=False)
        now = timestamp()
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO households VALUES (?, ?, ?, 0, ?)",
                (key, label, payload, now),
            )
            # 기존 가구가 있으면 원본 JSON이 바뀌어도 DB 데이터와 버전을 덮어쓰지 않는다.
            row = db.execute(
                "SELECT payload, revision, updated_at FROM households WHERE id=?", (key,)
            ).fetchone()
            db.execute(
                "INSERT OR IGNORE INTO household_versions VALUES (?, ?, ?, ?)",
                (key, row["revision"], row["payload"], row["updated_at"]),
            )

    def list_workspaces(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT id, label, revision, updated_at FROM households ORDER BY id"
                )
            ]

    def get(self, key: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM households WHERE id=?", (key,)).fetchone()
        if row is None:
            raise KeyError("가구 데이터를 찾을 수 없습니다")
        return {
            "id": row["id"],
            "label": row["label"],
            "revision": row["revision"],
            "updated_at": row["updated_at"],
            "household": json.loads(row["payload"]),
        }

    def save(self, key: str, data: dict[str, Any], expected_revision: int) -> dict[str, Any]:
        payload = json.dumps(clean_household(data), ensure_ascii=False)
        now = timestamp()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT revision FROM households WHERE id=?", (key,)).fetchone()
            if row is None:
                raise KeyError("가구 데이터를 찾을 수 없습니다")
            if row["revision"] != expected_revision:
                raise RevisionConflict(
                    "다른 창에서 데이터가 변경되었습니다. 새로고침한 뒤 변경 내용을 다시 확인하세요."
                )
            next_revision = expected_revision + 1
            db.execute(
                "UPDATE households SET payload=?, revision=?, updated_at=? WHERE id=?",
                (payload, next_revision, now, key),
            )
            db.execute(
                "INSERT INTO household_versions VALUES (?, ?, ?, ?)",
                (key, next_revision, payload, now),
            )
        return self.get(key)

    def backup_directory(self) -> Path:
        preferences = self.path.parent / "backup-settings.local.json"
        if preferences.exists():
            directory = json.loads(preferences.read_text(encoding="utf-8")).get("directory")
            if directory:
                return Path(directory)
        return self.path.parent / "backups"

    def set_backup_directory(self, directory: str) -> None:
        target = Path(directory).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        preferences = self.path.parent / "backup-settings.local.json"
        preferences.write_text(json.dumps({"directory": str(target)}), encoding="utf-8")

    def backup(self, *, daily: bool = False) -> Path:
        folder = self.backup_directory()
        folder.mkdir(parents=True, exist_ok=True)
        stamp = timestamp()[:10] if daily else timestamp().replace(":", "").replace("+", "-")
        target = folder / f"homeplan-{stamp}.sqlite"
        if daily and target.exists():
            return target
        if target.exists():
            import uuid

            target = target.with_stem(target.stem + "-" + uuid.uuid4().hex[:6])
        with self.connect() as source, sqlite3.connect(target) as destination:
            source.backup(destination)
        return target

    def backup_versions(self) -> list[dict[str, Any]]:
        folder = self.backup_directory()
        return [
            {"name": p.name, "size": p.stat().st_size}
            for p in sorted(folder.glob("homeplan-*.sqlite"), reverse=True)
        ]

    def backup_household(self, name: str, key: str) -> dict[str, Any]:
        if not re.fullmatch(r"homeplan-[\w+.-]+\.sqlite", name):
            raise ValueError("백업 파일 이름을 확인하세요")
        path = self.backup_directory() / name
        if not path.is_file():
            raise ValueError("백업 파일을 찾지 못했습니다")
        with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("백업 무결성 검사에 실패했습니다")
            row = db.execute("SELECT payload FROM households WHERE id=?", (key,)).fetchone()
            if row is None:
                raise ValueError("이 백업에는 선택한 계획이 없습니다")
        return clean_household(json.loads(row[0]))

    def history(self, key: str) -> list[dict[str, Any]]:
        self.get(key)
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT revision, saved_at FROM household_versions WHERE household_id=? ORDER BY revision DESC LIMIT 100",
                    (key,),
                )
            ]

    def version(self, key: str, revision: int) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute(
                "SELECT payload FROM household_versions WHERE household_id=? AND revision=?",
                (key, revision),
            ).fetchone()
        if row is None:
            raise KeyError("저장 버전을 찾을 수 없습니다")
        return dict(json.loads(row["payload"]))


def seed_repository(repo: Repository, root: Path) -> None:
    existing = {item["id"] for item in repo.list_workspaces()}
    actual = root / "data/household.local.json"
    if not existing and (root / "fresh-start.flag").is_file() and not actual.exists():
        from .workspaces import blank_plan

        data = blank_plan(datetime.now(timezone(timedelta(hours=9))).date())
        data["onboarding_pending"] = True
        repo.seed("actual", "내 계획 시작", data)
    if "actual" not in existing and actual.exists():
        repo.seed("actual", "실제 가구", json.loads(actual.read_text(encoding="utf-8-sig")))
    if "demo" not in existing:
        demo = root / "data/demo.local.json"
        if not demo.exists():
            demo = root / "tests/fixtures/synthetic_household.json"
        if not demo.exists():
            demo = Path(__file__).parent / "demo_household.json"
        if not demo.exists():
            demo = Path(__file__).parent / "synthetic_household.json"
        repo.seed("demo", "가상 테스트", json.loads(demo.read_text(encoding="utf-8-sig")))


def canonical_repository(path: Path) -> tuple[Repository, str] | None:
    root = Path(__file__).resolve().parents[2]
    names = {"household.local.json": "actual", "demo.local.json": "demo"}
    db_path = root / "data/homeplan.local.sqlite"
    if (
        path.name not in names
        or path.parent.resolve() != (root / "data").resolve()
        or not db_path.exists()
    ):
        return None
    repo = Repository(db_path)
    key = names[path.name]
    if key not in {row["id"] for row in repo.list_workspaces()}:
        return None
    return repo, key
