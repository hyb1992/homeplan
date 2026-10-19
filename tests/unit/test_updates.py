import hashlib
import json
import subprocess
import zipfile
from unittest.mock import patch

import pytest

from homeplan.updates import _managed_launch, prepare_update, release_url, stage_archive


@pytest.mark.parametrize(
    "name",
    [
        "../outside",
        "HomePlan/../outside",
        "HomePlan/data/keep.sqlite",
        "HomePlan/C:/outside",
        "HomePlan\\outside",
    ],
)
def test_update_rejects_traversal_and_user_data(tmp_path, name):
    archive = tmp_path / "update.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("HomePlan/HomePlan.exe", b"program")
        member = zipfile.ZipInfo(name)
        member.filename = name
        package.writestr(member, b"bad")
    with pytest.raises(ValueError):
        stage_archive(
            archive, tmp_path / "version", hashlib.sha256(archive.read_bytes()).hexdigest()
        )
    assert not (tmp_path / "version").exists()


def test_update_checks_hash_and_keeps_existing_data(tmp_path):
    archive = tmp_path / "update.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("HomePlan/HomePlan.exe", b"new-program")
    keep = tmp_path / "data/keep.local.json"
    keep.parent.mkdir()
    keep.write_bytes(b"existing-user-data")
    with pytest.raises(ValueError, match="무결성"):
        stage_archive(archive, tmp_path / "versions/bad", "0" * 64)
    exe = stage_archive(
        archive, tmp_path / "versions/good", hashlib.sha256(archive.read_bytes()).hexdigest()
    )
    assert exe.read_bytes() == b"new-program"
    assert keep.read_bytes() == b"existing-user-data"


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/hyb1992/homeplan/releases/download/a/b",
        "https://evil.test/a",
        "https://github.com/other/project/releases/download/a/b",
    ],
)
def test_update_source_is_fixed(url):
    with pytest.raises(ValueError):
        release_url(url)


@pytest.mark.parametrize("error", [OSError("offline"), TimeoutError("blocked")])
def test_offline_update_still_launches_current_app(tmp_path, error):
    with (
        patch("homeplan.gui_launcher.health", return_value=None),
        patch("homeplan.updates.prepare_update", side_effect=error),
        patch(
            "homeplan.updates.subprocess.run", return_value=subprocess.CompletedProcess([], 0)
        ) as run,
    ):
        _managed_launch(tmp_path)
    assert run.call_args.args[0] == [str(tmp_path / "HomePlan.exe")]
    assert run.call_args.kwargs["env"]["HOMEPLAN_DATA_ROOT"] == str(tmp_path.resolve())


def test_successful_update_preserves_database_versions_and_profile(tmp_path, household):
    from homeplan.repository import Repository

    repo = Repository(tmp_path / "data/homeplan.local.sqlite")
    repo.seed("actual", "Synthetic user's plan", household.model_dump(mode="json"))
    modified = repo.get("actual")["household"]
    modified["settings"]["husband_net_pay"] = 4321000
    original = repo.save("actual", modified, 0)
    history = repo.history("actual")
    profile = tmp_path / "data/edge.local.profile/keep"
    profile.parent.mkdir()
    profile.write_bytes(b"existing-browser-profile")
    state = {"build": "a" * 40, "published": "2026-10-19T00:00:00Z"}
    with (
        patch("homeplan.gui_launcher.health", return_value=None),
        patch("homeplan.updates.prepare_update", return_value=(tmp_path / "new.exe", state)),
        patch("homeplan.updates.subprocess.run", return_value=subprocess.CompletedProcess([], 0)),
    ):
        _managed_launch(tmp_path)
    assert repo.get("actual") == original
    assert repo.history("actual") == history
    assert (
        repo.version("actual", 0)["settings"]["husband_net_pay"]
        == household.settings.husband_net_pay
    )
    assert profile.read_bytes() == b"existing-browser-profile"
    backups = repo.backup_versions()
    assert backups and repo.backup_household(backups[0]["name"], "actual") == original["household"]


def test_failed_new_version_falls_back_and_does_not_commit_update_state(tmp_path):
    candidate = tmp_path / "versions/new/HomePlan.exe"
    with (
        patch("homeplan.gui_launcher.health", return_value=None),
        patch("homeplan.updates.prepare_update", return_value=(candidate, {"build": "new"})),
        patch(
            "homeplan.updates.subprocess.run",
            side_effect=[subprocess.CompletedProcess([], 1), subprocess.CompletedProcess([], 0)],
        ) as run,
    ):
        _managed_launch(tmp_path)
    assert run.call_args_list[0].args[0] == [str(candidate)]
    assert run.call_args_list[1].args[0] == [str(tmp_path / "HomePlan.exe")]
    assert not (tmp_path / "data/update-state.local.json").exists()


def test_existing_server_is_opened_without_replacing_code(tmp_path):
    instance = hashlib.sha256(
        str((tmp_path / "data/homeplan.local.sqlite").resolve()).encode()
    ).hexdigest()[:16]
    with (
        patch("homeplan.gui_launcher.health", return_value={"instance": instance}),
        patch("homeplan.gui_launcher.open_window") as open_window,
        patch("homeplan.updates.prepare_update") as prepare,
    ):
        _managed_launch(tmp_path)
    open_window.assert_called_once_with("http://127.0.0.1:8765")
    prepare.assert_not_called()


def test_same_build_does_not_download_archive():
    release = {
        "published_at": "2026-10-19T00:00:00Z",
        "assets": [
            {
                "name": name,
                "browser_download_url": f"https://github.com/hyb1992/homeplan/releases/download/test/{name}",
            }
            for name in ["HomePlan-Windows-x64.zip", "release.json"]
        ],
    }
    with patch(
        "homeplan.updates.fetch_bytes",
        side_effect=[json.dumps(release).encode(), json.dumps({"build": "a" * 40}).encode()],
    ) as fetch:
        executable, _ = prepare_update(None, {"build": "a" * 40})
    assert executable is None and fetch.call_count == 2
