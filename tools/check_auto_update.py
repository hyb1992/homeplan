"""Build a synthetic future app and verify a real frozen update on an isolated DB."""

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import expect, sync_playwright

from homeplan.gui_launcher import health
from homeplan.models import Household
from homeplan.repository import Repository
from homeplan.updates import ASSET, prepare_update

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    archive = parser.parse_args().archive.resolve()
    with tempfile.TemporaryDirectory(prefix="homeplan-auto-update-") as temporary:
        folder = Path(temporary)
        source = folder / "future-source"
        source.mkdir()
        for name in ("src", "web", "tools", "data/rules", "tests/fixtures"):
            shutil.copytree(
                ROOT / name,
                source / name,
                ignore=shutil.ignore_patterns("*.local.*", "__pycache__"),
            )
        shutil.copy2(ROOT / "README_PUBLIC.md", source / "README_PUBLIC.md")
        init = source / "src/homeplan/__init__.py"
        from homeplan import __version__

        init.write_text(init.read_text("utf-8").replace(__version__, "9.0.0"), "utf-8")
        spec = importlib.util.spec_from_file_location(
            "future_builder", ROOT / "tools/build_friend_package.py"
        )
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        builder.ROOT = source
        actual_version = builder.importlib.metadata.version
        with (
            patch.dict(os.environ, {"GITHUB_SHA": "b" * 40}),
            patch.object(
                builder.importlib.metadata,
                "version",
                side_effect=lambda name: "9.0.0" if name == "homeplan" else actual_version(name),
            ),
        ):
            builder.main()
        release_dir = Path(
            json.loads((source / "data/release-build.local.json").read_text())["directory"]
        )
        with zipfile.ZipFile(archive) as package:
            package.extractall(folder / "installed")
        root = folder / "installed/HomePlan"
        payload = Household.model_validate_json(
            (ROOT / "tests/fixtures/synthetic_household.json").read_text("utf-8")
        ).model_dump(mode="json")
        repo = Repository(root / "data/homeplan.local.sqlite")
        repo.seed("actual", "UPDATE_SYNTHETIC_ONLY", payload)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        environment = {**os.environ, "HOMEPLAN_DATA_ROOT": str(root), "HOMEPLAN_MANAGED_CHILD": "1"}
        environment.pop("HOMEPLAN_DISABLE_UPDATES", None)
        process = subprocess.Popen(
            [str(root / "HomePlan.exe"), "--serve", "--port", str(port)], cwd=root, env=environment
        )
        candidate_pid = None
        try:
            for _ in range(200):
                if health(port):
                    break
                time.sleep(0.1)
            assert health(port)["version"] == __version__
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="msedge")
                page = browser.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                url = f"http://127.0.0.1:{port}/#settings"
                page.goto(url)
                expect(page.locator("#field-husband_net_pay")).to_be_visible(timeout=30000)
                page.evaluate("localStorage.setItem('update-preserve-marker','synthetic-profile')")
                page.locator("#field-husband_net_pay").fill("777만원")
                page.locator("#field-husband_net_pay").press("Tab")
                page.wait_for_timeout(400)
                draft = page.evaluate(
                    "Object.entries(localStorage).find(([key])=>key.startsWith('homeplan-draft:'))?.[1]"
                )
                assert draft
                before = repo.get("actual")
                history = repo.history("actual")
                digest = hashlib.sha256(repo.path.read_bytes()).hexdigest()
                prefix = "https://github.com/hyb1992/homeplan/releases/download/synthetic/"
                release = {
                    "tag_name": "v9.0.0",
                    "target_commitish": "b" * 40,
                    "assets": [
                        {"name": name, "browser_download_url": prefix + name}
                        for name in (ASSET, "SHA256SUMS.txt")
                    ],
                }
                with patch(
                    "homeplan.updates.fetch_bytes",
                    side_effect=lambda url, *_args: (
                        release_dir / url.rsplit("/", 1)[1]
                    ).read_bytes(),
                ):
                    assert prepare_update(root, release).is_file()
                page.locator("#update-check").click()
                expect(page.locator("#update-state")).to_contain_text("편집", timeout=15000)
                assert health(port)["version"] == __version__
                assert repo.get("actual") == before and repo.history("actual") == history
                assert hashlib.sha256(repo.path.read_bytes()).hexdigest() == digest
                assert (
                    page.evaluate(
                        "Object.entries(localStorage).find(([key])=>key.startsWith('homeplan-draft:'))?.[1]"
                    )
                    == draft
                )
                page.locator("#save-button").click()
                expect(page.locator("#modal-title")).to_contain_text("저장", timeout=30000)
                page.get_by_role("button", name="확인하고 저장", exact=True).click()
                expect(page.locator("#save-state")).to_contain_text("저장된", timeout=30000)
                saved, saved_history = repo.get("actual"), repo.history("actual")
                for _ in range(300):
                    status = health(port)
                    if status and status["version"] == "9.0.0":
                        candidate_pid = status["pid"]
                        break
                    page.wait_for_timeout(200)
                assert candidate_pid, "Prepared frozen app did not start"
                expect(page.locator("#update-state")).to_contain_text("v9.0.0", timeout=30000)
                assert page.url == url
                assert repo.get("actual") == saved and repo.history("actual") == saved_history
                assert saved["household"]["settings"]["husband_net_pay"] == 7770000
                assert (
                    page.evaluate("localStorage.getItem('update-preserve-marker')")
                    == "synthetic-profile"
                )
                assert list((root / "data/backups").glob("*.sqlite"))
                assert not errors, errors
                browser.close()
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=15)
            if candidate_pid:
                import signal

                os.kill(candidate_pid, signal.SIGTERM)
        print(
            "PASS: real frozen automatic update; deferred during edits; same origin; DB/history/profile preserved; pre-update backup"
        )


if __name__ == "__main__":
    main()
