"""전달 ZIP을 깨끗한 폴더에 풀어 실제 EXE의 초기화·저장·재실행을 검사한다."""

import argparse
import json
import os
import socket
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    archive = parser.parse_args().archive
    with tempfile.TemporaryDirectory(prefix="homeplan-friend-") as folder:
        root = Path(folder) / "친구 PC 테스트"
        root.mkdir()
        with zipfile.ZipFile(archive) as package:
            for name in package.namelist():
                path = root / name
                if not path.resolve().is_relative_to(root.resolve()):
                    raise ValueError("ZIP 경로를 확인하세요")
                assert ".local." not in name and not name.endswith((".sqlite", ".xlsx", ".bak"))
            package.extractall(root)
        executable = root / "HomePlan/HomePlan.exe"
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        environment.pop("PYTHONHOME", None)
        environment["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")

        def start() -> subprocess.Popen[bytes]:
            process = subprocess.Popen(
                [str(executable), "--serve", "--port", str(port)],
                cwd=root,
                env=environment,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            for _ in range(100):
                if process.poll() is not None:
                    log = root / "HomePlan/data/gui.local.log"
                    raise RuntimeError(log.read_text("utf-8") if log.exists() else "EXE stopped")
                try:
                    if httpx.get(base + "/api/health").status_code == 200:
                        return process
                except httpx.ConnectError:
                    pass
                time.sleep(0.1)
            process.terminate()
            raise RuntimeError("EXE startup timed out")

        process = start()
        try:
            actual = httpx.get(base + "/api/workspaces/actual").json()["household"]
            assert actual["fund_events"] == [] and actual["parent_support"] == []
            assert actual["loan_prepayments"] == [] and actual["listings"][0]["price"] == 0
            assert actual["settings"]["mortgage_desired"] == 0
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="msedge", headless=True)
                page = browser.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base)
                expect(page.locator("#upgrade-new")).to_be_visible(timeout=15000)
                page.locator("#upgrade-label").fill("FRIEND_TEST_ONLY")
                page.get_by_role("button", name="다음", exact=True).click()
                page.locator("#upgrade-cash").fill("1234만원")
                page.locator("#upgrade-husband").fill("400만원")
                page.locator("#upgrade-living").fill("200만원")
                page.get_by_role("button", name="다음", exact=True).click()
                page.locator("#upgrade-price").fill("5억원")
                page.get_by_role("button", name="다음", exact=True).click()
                page.get_by_role("button", name="새 계획 저장", exact=True).click()
                expect(page.locator("#upgrade-new")).not_to_be_visible(timeout=15000)
                assert not errors, errors
                browser.close()
            workspaces = httpx.get(base + "/api/workspaces").json()
            key = next(row["id"] for row in workspaces if row["label"] == "FRIEND_TEST_ONLY")
            stored = httpx.get(base + f"/api/workspaces/{key}").json()
            assert stored["household"]["fund_events"][0]["value"] == 12340000
        finally:
            process.terminate()
            process.wait(timeout=10)
        process = start()
        try:
            restored = httpx.get(base + f"/api/workspaces/{key}").json()
            assert restored == stored
            assert httpx.get(base + "/api/workspaces/actual").json()["household"] == actual
        finally:
            process.terminate()
            process.wait(timeout=10)
    print(
        json.dumps(
            {
                "portable_exe": "passed",
                "initial_values": "zero",
                "onboarding": "passed",
                "save_restart": "passed",
                "python_on_path": False,
            }
        )
    )


if __name__ == "__main__":
    main()
