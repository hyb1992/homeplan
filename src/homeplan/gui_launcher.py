"""콘솔 없이 로컬 서버를 준비하고 브라우저 앱 창을 연다."""

import argparse
import ctypes
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

from .updates import data_root


def health(port: int) -> dict[str, Any] | None:
    try:
        # OS 프록시 설정과 무관하게 이 컴퓨터의 루프백에만 연결한다.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{port}/api/health", timeout=0.6) as response:
            value = json.load(response)
            return value if isinstance(value, dict) else None
    except (OSError, ValueError, urllib.error.URLError):
        return None


def ensure_server(root: Path) -> str:
    db_path = root / "data/homeplan.local.sqlite"
    instance = hashlib.sha256(str(db_path.resolve()).encode()).hexdigest()[:16]
    for port in range(8765, 8775):
        status = health(port)
        if (
            status
            and status.get("service") == "homeplan-gui"
            and status.get("instance") == instance
        ):
            return f"http://127.0.0.1:{port}"
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
        log_path = root / "data/gui.local.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log:
            child = subprocess.Popen(
                (
                    [sys.executable, "--serve", "--port", str(port)]
                    if getattr(sys, "frozen", False)
                    else [sys.executable, "-m", "homeplan.server", "--port", str(port)]
                ),
                cwd=root,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        for _ in range(150):
            status = health(port)
            if status and status.get("instance") == instance:
                return f"http://127.0.0.1:{port}"
            if child.poll() is not None:
                break
            time.sleep(0.1)
        if child.poll() is None:
            child.terminate()
        raise RuntimeError("화면을 준비하지 못했습니다. data/gui.local.log를 확인해 주세요.")
    raise RuntimeError("실행 포트를 사용 중입니다. 기존 앱을 닫고 다시 실행해 주세요.")


def browser_profile(root: Path, browser: str) -> Path:
    profile = root / "data" / f"{browser}.local.profile"
    preferences = profile / "Default" / "Preferences"
    preferences.parent.mkdir(parents=True, exist_ok=True)
    # 최초 실행 전에 설정한다. 실행 중인 브라우저의 설정 파일을 덮어쓰지 않는다.
    try:
        with preferences.open("x", encoding="utf-8") as output:
            json.dump(
                {
                    "autofill": {"profile_enabled": False, "credit_card_enabled": False},
                    "credentials_enable_service": False,
                    "profile": {"password_manager_enabled": False},
                },
                output,
            )
    except FileExistsError:
        pass
    return profile


def open_window(url: str) -> None:
    candidates = [
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
        / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        / "Google/Chrome/Application/chrome.exe",
    ]
    for browser in candidates:
        if browser.exists():
            root = data_root()
            profile = browser_profile(root, "edge" if browser.stem == "msedge" else "chrome")
            subprocess.Popen(
                [
                    str(browser),
                    f"--user-data-dir={profile}",
                    f"--app={url}",
                    "--window-size=1440,1000",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
    webbrowser.open(url, new=1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = data_root()
    if args.check:
        from .server import create_app

        create_app()
        print("GUI 준비 완료: 입력 화면·앱 DB·계산 엔진")
        return
    try:
        url = ensure_server(root)
        if not os.environ.get("HOMEPLAN_NO_WINDOW"):
            open_window(url)
    except Exception as exc:
        if sys.platform == "win32":
            ctypes.windll.user32.MessageBoxW(None, str(exc), "우리집 매수계획 · 실행 오류", 0x10)
            raise SystemExit(1) from exc
        else:
            raise


if __name__ == "__main__":
    main()
