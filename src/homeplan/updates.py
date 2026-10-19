"""공개 GitHub 릴리스의 검증된 프로그램만 별도 버전 폴더에 설치한다."""

import hashlib
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from . import __version__

REPOSITORY = "hyb1992/homeplan"
API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
ASSET = "HomePlan-Windows-x64.zip"


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


def fetch_release() -> dict[str, Any] | None:
    """공개 배포 정보만 확인한다. 다운로드/설치/DB 변경은 하지 않는다."""
    if os.environ.get("HOMEPLAN_DISABLE_UPDATES"):
        return None
    request = urllib.request.Request(
        API,
        headers={"User-Agent": "HomePlan-Version-Check", "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=4) as response:
            payload = response.read(1024 * 1024 + 1)
        if len(payload) > 1024 * 1024:
            return None
        value = json.loads(payload)
        if not isinstance(value, dict):
            return None
        assets = []
        for item in value.get("assets", []):
            if item.get("name") == ASSET:
                assets.append(
                    {
                        "name": ASSET,
                        "browser_download_url": release_url(item["browser_download_url"]),
                    }
                )
        return {
            key: value.get(key) for key in ("tag_name", "target_commitish", "draft", "prerelease")
        } | {"assets": assets}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def version_tuple(value: str) -> tuple[int, int, int]:
    found = re.match(r"^v?(\d+)\.(\d+)\.(\d+)(?:$|[-+])", value)
    return (int(found[1]), int(found[2]), int(found[3])) if found else (0, 0, 0)


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
    """설치된 버전만 실행한다. 네트워크/설치/원장을 변경하지 않는다."""
    from .gui_launcher import health, open_window

    root = root.resolve()
    folder = root / "data"
    folder.mkdir(parents=True, exist_ok=True)
    instance = hashlib.sha256(
        str((folder / "homeplan.local.sqlite").resolve()).encode()
    ).hexdigest()[:16]
    current = root / "HomePlan.exe"
    # 0.4.0에서 이미 설치한 버전은 보존하되 새 패키지보다 오래된 실행 파일은 선택하지 않는다.
    try:
        state = json.loads((folder / "update-state.local.json").read_text("utf-8"))
        build = state.get("build", "")
        if isinstance(build, str) and re.fullmatch(r"[0-9a-f]{40}", build):
            app = root / "versions" / build / "HomePlan"
            info = json.loads((app / "_internal/homeplan/build-info.json").read_text("utf-8"))
            if (
                version_tuple(str(info.get("version", ""))) > version_tuple(__version__)
                and (app / "HomePlan.exe").is_file()
            ):
                current = app / "HomePlan.exe"
    except (OSError, ValueError, AttributeError):
        pass
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
    environment = {**os.environ, "HOMEPLAN_DATA_ROOT": str(root), "HOMEPLAN_MANAGED_CHILD": "1"}
    result = subprocess.run([str(current)], cwd=root, env=environment, check=False)
    if result.returncode:
        raise RuntimeError("프로그램 실행에 실패했습니다. data/gui.local.log를 확인하세요.")
