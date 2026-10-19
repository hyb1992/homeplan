"""공개 GitHub 릴리스의 검증된 프로그램만 별도 버전 폴더에 설치한다."""

import hashlib
import json
import os
import re
import subprocess
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

REPOSITORY = "hyb1992/homeplan"
API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
ASSET = "HomePlan-Windows-x64.zip"
MAX_ARCHIVE = 150 * 1024 * 1024


def data_root() -> Path:
    configured = os.environ.get("HOMEPLAN_DATA_ROOT")
    return Path(configured).resolve() if configured else Path(__file__).resolve().parents[2]


def build_id() -> str:
    path = Path(__file__).parent / "build-info.json"
    return str(json.loads(path.read_text("utf-8"))["build"]) if path.exists() else "development"


def release_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or not parsed.path.startswith(f"/{REPOSITORY}/releases/download/")
        or parsed.username
        or parsed.password
    ):
        raise ValueError("허용되지 않은 업데이트 다운로드 주소입니다")
    return url


def fetch_bytes(url: str, limit: int, timeout: int = 4) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": "HomePlan-Updater", "Accept": "application/vnd.github+json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("업데이트 파일이 허용된 크기를 초과합니다")
    return bytes(data)


def stage_archive(archive: Path, destination: Path, expected: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("업데이트 해시가 잘못되었습니다")
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
        raise ValueError("업데이트 파일 무결성 확인에 실패했습니다")
    if destination.exists():
        raise ValueError("새 버전 폴더가 이미 존재합니다")
    with zipfile.ZipFile(archive) as package:
        members = package.infolist()
        total = 0
        seen = set()
        for item in members:
            path = PurePosixPath(item.filename)
            parts = path.parts
            raw_parts = item.orig_filename.rstrip("/").split("/")
            if (
                "\\" in item.orig_filename
                or not parts
                or parts[0] != "HomePlan"
                or path.is_absolute()
                or any(p in {".", ".."} or ":" in p for p in parts)
                or any(p != p.rstrip(" .") or not p for p in raw_parts)
                or (len(parts) > 1 and parts[1].lower() in {"data", "versions"})
                or ".local." in item.filename.lower()
                or path.suffix.lower() in {".sqlite", ".db", ".xlsx", ".xls", ".bak"}
                or (item.external_attr >> 16) & 0o170000 == 0o120000
                or item.filename.casefold() in seen
            ):
                raise ValueError("업데이트 ZIP에 허용되지 않은 경로가 있습니다")
            seen.add(item.filename.casefold())
            total += item.file_size
        if total > 500 * 1024 * 1024 or len(members) > 10000:
            raise ValueError("압축을 푼 업데이트 파일이 너무 큽니다")
        if "homeplan/homeplan.exe" not in seen:
            raise ValueError("업데이트 실행 파일이 없습니다")
        destination.mkdir(parents=True)
        package.extractall(destination)
    return destination / "HomePlan/HomePlan.exe"


def prepare_update(root: Path, state: dict[str, Any]) -> tuple[Path | None, dict[str, Any]]:
    release = json.loads(fetch_bytes(API, 1024 * 1024, timeout=4))
    if release.get("draft") or release.get("prerelease"):
        return None, state
    assets = {item["name"]: item for item in release.get("assets", [])}
    if not {ASSET, "release.json"}.issubset(assets):
        return None, state
    manifest = json.loads(
        fetch_bytes(release_url(assets["release.json"]["browser_download_url"]), 16384)
    )
    build = manifest["build"]
    if not re.fullmatch(r"[0-9a-f]{40}", build):
        raise ValueError("업데이트 버전 식별자가 잘못되었습니다")
    if build in {state.get("build"), build_id()}:
        return None, state
    published = str(release.get("published_at", ""))
    if published <= state.get("published", ""):
        return None, state
    folder = root / "versions" / build
    executable = folder / "HomePlan/HomePlan.exe"
    if not executable.is_file():
        data = fetch_bytes(
            release_url(assets[ASSET]["browser_download_url"]), MAX_ARCHIVE, timeout=8
        )
        with tempfile.TemporaryDirectory(prefix="homeplan-update-") as temporary:
            archive = Path(temporary) / "program.zip"
            archive.write_bytes(data)
            executable = stage_archive(archive, folder, manifest["sha256"])
    return executable, {"build": build, "published": published}


def managed_launch(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(exist_ok=True)
    with (root / "data/update-lock.local.bin").open("a+b") as lock:
        if os.name == "nt":
            import msvcrt

            lock.seek(0)
            lock.write(b"0")
            lock.flush()
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                return
        _managed_launch(root)


def _managed_launch(root: Path) -> None:
    """실행 중인 서버가 있으면 유지한다. 다음 실행에서 준비된 새 버전을 사용한다."""
    from .gui_launcher import health, open_window

    root = root.resolve()
    folder = root / "data"
    folder.mkdir(parents=True, exist_ok=True)
    instance = hashlib.sha256(
        str((folder / "homeplan.local.sqlite").resolve()).encode()
    ).hexdigest()[:16]
    state_path = folder / "update-state.local.json"
    try:
        state = json.loads(state_path.read_text("utf-8")) if state_path.exists() else {}
        if not isinstance(state, dict) or not re.fullmatch(
            r"[0-9a-f]{40}", str(state.get("build", ""))
        ):
            state = {}
    except (OSError, ValueError):
        state = {}
    current = root / "versions" / str(state.get("build", "")) / "HomePlan/HomePlan.exe"
    if not current.is_file():
        current = root / "HomePlan.exe"
    live = next(
        (
            port
            for port in range(8765, 8775)
            if (status := health(port)) and status.get("instance") == instance
        ),
        None,
    )
    if live:
        open_window(f"http://127.0.0.1:{live}")
        return
    candidate = None
    new_state = state
    try:
        if not os.environ.get("HOMEPLAN_DISABLE_UPDATES"):
            candidate, new_state = prepare_update(root, state)
    except Exception as error:
        with (folder / "updates.local.log").open("a", encoding="utf-8") as log:
            log.write(f"Update deferred: {type(error).__name__}: {error}\n")
    environment = {**os.environ, "HOMEPLAN_DATA_ROOT": str(root), "HOMEPLAN_MANAGED_CHILD": "1"}
    if candidate and (folder / "homeplan.local.sqlite").exists():
        from .repository import Repository

        try:
            Repository(folder / "homeplan.local.sqlite").backup()
        except Exception:
            candidate = None
    executable = candidate or current
    result = subprocess.run([str(executable)], cwd=root, env=environment, check=False)
    if result.returncode and candidate:
        subprocess.run([str(current)], cwd=root, env=environment, check=True)
        return
    if result.returncode:
        raise RuntimeError("프로그램 실행에 실패했습니다. data/gui.local.log를 확인하세요.")
    if candidate:
        temporary = state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(new_state), "utf-8")
        temporary.replace(state_path)
