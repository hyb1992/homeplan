"""공개 GitHub 릴리스의 검증된 프로그램만 별도 버전 폴더에 설치한다."""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from . import __version__

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


def fetch_release() -> dict[str, Any] | None:
    """공개 배포 정보만 조회한다. 다운로드는 별도 백그라운드 작업에서 수행한다."""
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
            if item.get("name") in {ASSET, "SHA256SUMS.txt"}:
                assets.append(
                    {
                        "name": item["name"],
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


def fetch_bytes(url: str, limit: int, timeout: int = 12) -> bytes:
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


def installed_update(root: Path) -> Path | None:
    """Only select a fully staged, newer app; the original data root never moves."""
    try:
        state = json.loads((root / "data/update-state.local.json").read_text("utf-8"))
        build = state["build"]
        if state.get("failed"):
            return None
        if not isinstance(build, str) or not re.fullmatch(r"[0-9a-f]{40}", build):
            return None
        app = root / "versions" / build / "HomePlan"
        info = json.loads((app / "_internal/homeplan/build-info.json").read_text("utf-8"))
        executable = app / "HomePlan.exe"
        if (
            version_tuple(str(info.get("version", ""))) > version_tuple(__version__)
            and executable.is_file()
        ):
            return executable
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def prepare_update(root: Path, release: dict[str, Any]) -> Path | None:
    """Download and validate code in isolation, without opening the user's database."""
    if (
        os.environ.get("HOMEPLAN_DISABLE_UPDATES")
        or release.get("draft")
        or release.get("prerelease")
    ):
        return None
    if version_tuple(str(release.get("tag_name", ""))) <= version_tuple(__version__):
        return None
    build = release.get("target_commitish", "")
    if not isinstance(build, str) or not re.fullmatch(r"[0-9a-f]{40}", build):
        raise ValueError("업데이트 버전 식별자가 잘못되었습니다")
    assets = {item["name"]: item for item in release.get("assets", [])}
    if not {ASSET, "SHA256SUMS.txt"}.issubset(assets):
        raise ValueError("업데이트 검증 파일이 없습니다")
    checksum = fetch_bytes(
        release_url(assets["SHA256SUMS.txt"]["browser_download_url"]), 16384
    ).decode("ascii")
    matches = re.findall(r"(?m)^([0-9a-f]{64})  HomePlan-Windows-x64\.zip\s*$", checksum)
    if len(matches) != 1:
        raise ValueError("업데이트 체크섬이 잘못되었습니다")
    state_path = root / "data/update-state.local.json"
    if state_path.exists():
        state = json.loads(state_path.read_text("utf-8"))
        if state.get("build") == build and state.get("failed"):
            raise ValueError("실행에 실패한 버전은 다시 적용하지 않습니다")
    versions = root / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    destination = versions / build
    # Extract to a temporary sibling; incomplete downloads never become launch candidates.
    with tempfile.TemporaryDirectory(prefix=".stage-", dir=versions) as directory:
        temporary = Path(directory)
        archive = temporary / "program.zip"
        archive.write_bytes(
            fetch_bytes(release_url(assets[ASSET]["browser_download_url"]), MAX_ARCHIVE)
        )
        staged = stage_archive(archive, temporary / "extracted", matches[0])
        info = json.loads((staged.parent / "_internal/homeplan/build-info.json").read_text("utf-8"))
        if info.get("build") != build or version_tuple(
            str(info.get("version", ""))
        ) != version_tuple(str(release["tag_name"])):
            raise ValueError("업데이트 파일의 버전이 배포 정보와 다릅니다")
        if not destination.exists():
            (temporary / "extracted").rename(destination)
        else:
            existing = destination / "HomePlan/_internal/homeplan/build-info.json"
            if json.loads(existing.read_text("utf-8")) != info:
                raise ValueError("기존 업데이트 폴더가 배포 정보와 다릅니다")
    folder = root / "data"
    folder.mkdir(parents=True, exist_ok=True)
    state = folder / "update-state.local.json"
    pending = state.with_suffix(".tmp")
    pending.write_text(json.dumps({"build": build, "version": info["version"]}), "utf-8")
    pending.replace(state)
    return destination / "HomePlan/HomePlan.exe"


class UpdatePreparation:
    """One optional background download per server, outside the startup path."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.status = "source" if not getattr(sys, "frozen", False) else "idle"
        self.lock = threading.Lock()

    def start(self, release: dict[str, Any] | None) -> None:
        if self.status == "source" or os.environ.get("HOMEPLAN_DISABLE_UPDATES"):
            return
        with self.lock:
            if self.status in {"downloading", "ready"}:
                return
            if installed_update(self.root):
                self.status = "ready"
                return
            if not release:
                return
            if version_tuple(str(release.get("tag_name", ""))) <= version_tuple(__version__):
                self.status = "idle"
                return
            self.status = "downloading"

        def work() -> None:
            try:
                self.status = "ready" if prepare_update(self.root, release) else "idle"
            except Exception as error:
                self.status = "skipped"
                # Diagnostics contain no financial inputs.
                with (self.root / "data/updates.local.log").open("a", encoding="utf-8") as log:
                    log.write(f"Update deferred: {type(error).__name__}\n")

        threading.Thread(target=work, daemon=True).start()


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
    """Launch prepared code immediately, without network on the startup path."""
    from .gui_launcher import health, open_window

    root = root.resolve()
    folder = root / "data"
    folder.mkdir(parents=True, exist_ok=True)
    instance = hashlib.sha256(
        str((folder / "homeplan.local.sqlite").resolve()).encode()
    ).hexdigest()[:16]
    base = Path(os.environ.get("HOMEPLAN_BASE_EXE", str(root / "HomePlan.exe")))
    current = base
    current = installed_update(root) or current
    live = next(
        (
            port
            for port in range(8765, 8775)
            if (status := health(port))
            and status.get("instance") == instance
            and status.get("managed") is True
        ),
        None,
    )
    if live:
        open_window(f"http://127.0.0.1:{live}")
        return
    environment = {**os.environ, "HOMEPLAN_DATA_ROOT": str(root), "HOMEPLAN_MANAGED_CHILD": "1"}
    if current != base and (folder / "homeplan.local.sqlite").exists():
        from .repository import Repository

        Repository(folder / "homeplan.local.sqlite").backup()
    try:
        result = subprocess.run([str(current)], cwd=root, env=environment, check=False)
    except OSError:
        if current == base:
            raise
        result = subprocess.CompletedProcess([str(current)], 1)
    if result.returncode and current != base:
        reject_update(root)
        subprocess.run([str(base)], cwd=root, env=environment, check=True)
        return
    if result.returncode:
        raise RuntimeError("프로그램 실행에 실패했습니다. data/gui.local.log를 확인하세요.")


def reject_update(root: Path) -> None:
    state_path = root / "data/update-state.local.json"
    state = json.loads(state_path.read_text("utf-8"))
    state["failed"] = True
    temporary = state_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state), "utf-8")
    temporary.replace(state_path)


def restart_server(port: int) -> None:
    """Replace only the server; preserve origin, browser profile and data root."""
    from .gui_launcher import health

    root = data_root()
    candidate = installed_update(root)
    if not candidate or not 8765 <= port <= 65535:
        return
    for _ in range(150):
        if health(port) is None:
            break
        time.sleep(0.1)
    else:
        return
    environment = {**os.environ, "HOMEPLAN_DATA_ROOT": str(root), "HOMEPLAN_MANAGED_CHILD": "1"}
    with (root / "data/gui.local.log").open("a", encoding="utf-8") as log:
        process = None
        try:
            process = subprocess.Popen(
                [str(candidate), "--serve", "--port", str(port)],
                cwd=root,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            expected = json.loads(
                (candidate.parent / "_internal/homeplan/build-info.json").read_text("utf-8")
            )["version"]
            instance = hashlib.sha256(
                str((root / "data/homeplan.local.sqlite").resolve()).encode()
            ).hexdigest()[:16]
            for _ in range(200):
                status = health(port)
                if (
                    status
                    and status.get("instance") == instance
                    and status.get("version") == expected
                ):
                    return
                if process.poll() is not None:
                    break
                time.sleep(0.1)
        except OSError:
            pass
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        reject_update(root)
        subprocess.Popen(
            [sys.executable, "--serve", "--port", str(port)],
            cwd=root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
