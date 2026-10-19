import hashlib
import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from homeplan.updates import (
    ASSET,
    UpdatePreparation,
    _managed_launch,
    fetch_release,
    prepare_update,
    release_url,
    stage_archive,
)


def test_detection_only_reads_one_metadata_response(tmp_path):
    value = {
        "tag_name": "v0.4.2",
        "target_commitish": "a" * 40,
        "assets": [
            {
                "name": ASSET,
                "browser_download_url": "https://github.com/hyb1992/homeplan/releases/download/v0.4.2/"
                + ASSET,
            },
            {"name": "release.json", "browser_download_url": "https://example.invalid/never-read"},
        ],
    }
    stream = MagicMock()
    stream.__enter__.return_value.read.return_value = json.dumps(value).encode()
    with patch("homeplan.updates.urllib.request.urlopen", return_value=stream) as request:
        release = fetch_release()
    assert release["tag_name"] == "v0.4.2" and len(release["assets"]) == 1
    assert request.call_count == 1
    assert request.call_args.args[0].data is None
    assert request.call_args.kwargs["timeout"] == 4
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("error", [OSError("offline"), TimeoutError("blocked")])
def test_failed_detection_is_skipped(error):
    with patch("homeplan.updates.urllib.request.urlopen", side_effect=error):
        assert fetch_release() is None


def test_disabled_detection_does_not_contact_github(monkeypatch):
    monkeypatch.setenv("HOMEPLAN_DISABLE_UPDATES", "1")
    with patch("homeplan.updates.urllib.request.urlopen") as request:
        assert fetch_release() is None
    request.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/hyb1992/homeplan/releases/download/a/b",
        "https://evil.test/a",
        "https://github.com/other/project/releases/download/a/b",
    ],
)
def test_download_source_is_fixed(url):
    with pytest.raises(ValueError):
        release_url(url)


def test_launcher_never_checks_downloads_or_changes_user_data(tmp_path, household):
    from homeplan.repository import Repository

    repo = Repository(tmp_path / "data/homeplan.local.sqlite")
    repo.seed("actual", "Synthetic plan", household.model_dump(mode="json"))
    modified = repo.get("actual")["household"]
    modified["settings"]["husband_net_pay"] = 4321000
    original = repo.save("actual", modified, 0)
    history = repo.history("actual")
    digest = hashlib.sha256(repo.path.read_bytes()).hexdigest()
    profile = tmp_path / "data/edge.local.profile/keep"
    profile.parent.mkdir()
    profile.write_bytes(b"existing-browser-profile")
    with (
        patch("homeplan.gui_launcher.health", return_value=None),
        patch("homeplan.updates.urllib.request.urlopen") as network,
        patch(
            "homeplan.updates.subprocess.run", return_value=subprocess.CompletedProcess([], 0)
        ) as run,
    ):
        _managed_launch(tmp_path)
    network.assert_not_called()
    assert run.call_args.args[0] == [str(tmp_path / "HomePlan.exe")]
    assert run.call_args.kwargs["env"]["HOMEPLAN_DATA_ROOT"] == str(tmp_path.resolve())
    assert hashlib.sha256(repo.path.read_bytes()).hexdigest() == digest
    assert repo.get("actual") == original and repo.history("actual") == history
    assert profile.read_bytes() == b"existing-browser-profile"
    assert not (tmp_path / "versions").exists()


@pytest.mark.parametrize("version, expected", [("0.4.0", False), ("9.0.0", True)])
def test_previously_installed_version_remains_compatible(tmp_path, version, expected):
    app = tmp_path / "versions" / ("a" * 40) / "HomePlan"
    info = app / "_internal/homeplan/build-info.json"
    info.parent.mkdir(parents=True)
    info.write_text(json.dumps({"version": version}))
    (app / "HomePlan.exe").write_bytes(b"existing")
    (tmp_path / "data").mkdir()
    (tmp_path / "data/update-state.local.json").write_text(json.dumps({"build": "a" * 40}))
    with (
        patch("homeplan.gui_launcher.health", return_value=None),
        patch(
            "homeplan.updates.subprocess.run", return_value=subprocess.CompletedProcess([], 0)
        ) as run,
    ):
        _managed_launch(tmp_path)
    assert run.call_args.args[0] == [
        str(app / "HomePlan.exe" if expected else tmp_path / "HomePlan.exe")
    ]


def test_existing_server_is_opened_without_replacing_code(tmp_path):
    instance = hashlib.sha256(
        str((tmp_path / "data/homeplan.local.sqlite").resolve()).encode()
    ).hexdigest()[:16]
    with (
        patch("homeplan.gui_launcher.health", return_value={"instance": instance, "managed": True}),
        patch("homeplan.gui_launcher.open_window") as open_window,
        patch("homeplan.updates.urllib.request.urlopen") as network,
    ):
        _managed_launch(tmp_path)
    open_window.assert_called_once_with("http://127.0.0.1:8765")
    network.assert_not_called()


def release_fixture(tmp_path, *, corrupt=False, member="HomePlan/extra.txt"):
    import zipfile

    archive = tmp_path / "synthetic.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("HomePlan/HomePlan.exe", b"synthetic-code-only")
        package.writestr(
            "HomePlan/_internal/homeplan/build-info.json",
            json.dumps({"build": "b" * 40, "version": "9.0.0"}),
        )
        package.writestr(member, b"public")
    prefix = "https://github.com/hyb1992/homeplan/releases/download/test/"
    release = {
        "tag_name": "v9.0.0",
        "target_commitish": "b" * 40,
        "assets": [
            {"name": name, "browser_download_url": prefix + name}
            for name in (ASSET, "SHA256SUMS.txt")
        ],
    }
    digest = "0" * 64 if corrupt else hashlib.sha256(archive.read_bytes()).hexdigest()
    payloads = {
        prefix + ASSET: archive.read_bytes(),
        prefix + "SHA256SUMS.txt": (digest + "  " + ASSET + "\n").encode(),
    }
    return release, payloads, archive


def test_staging_preserves_database_history_and_browser_draft(tmp_path, household):
    from homeplan.repository import Repository

    repo = Repository(tmp_path / "data/homeplan.local.sqlite")
    repo.seed("actual", "Synthetic", household.model_dump(mode="json"))
    before, history = repo.get("actual"), repo.history("actual")
    digest = hashlib.sha256(repo.path.read_bytes()).hexdigest()
    draft = tmp_path / "data/edge.local.profile/draft"
    draft.parent.mkdir()
    draft.write_bytes(b"unsaved-browser-input")
    release, payloads, _ = release_fixture(tmp_path)
    with patch("homeplan.updates.fetch_bytes", side_effect=lambda url, *args: payloads[url]):
        executable = prepare_update(tmp_path, release)
    assert executable.is_file()
    assert json.loads((tmp_path / "data/update-state.local.json").read_text())["build"] == "b" * 40
    assert repo.get("actual") == before and repo.history("actual") == history
    assert hashlib.sha256(repo.path.read_bytes()).hexdigest() == digest
    assert draft.read_bytes() == b"unsaved-browser-input"


@pytest.mark.parametrize(
    "member",
    [
        "HomePlan/../evil.exe",
        "HomePlan/data/user.sqlite",
        "HomePlan/file.local.json",
        "HomePlan/C:/bad",
        "HomePlan/dir./bad",
    ],
)
def test_archive_rejects_private_files_and_escaping_paths(tmp_path, member):
    _, _, archive = release_fixture(tmp_path, member=member)
    with pytest.raises(ValueError):
        stage_archive(
            archive, tmp_path / "destination", hashlib.sha256(archive.read_bytes()).hexdigest()
        )
    assert not (tmp_path / "destination").exists()


def test_corrupt_download_does_not_activate_update(tmp_path):
    release, payloads, _ = release_fixture(tmp_path, corrupt=True)
    with patch("homeplan.updates.fetch_bytes", side_effect=lambda url, *args: payloads[url]):
        with pytest.raises(ValueError):
            prepare_update(tmp_path, release)
    assert not (tmp_path / "data/update-state.local.json").exists()
    assert not (tmp_path / "versions" / ("b" * 40)).exists()


def test_failed_background_update_never_blocks_startup(tmp_path, monkeypatch):
    import threading

    (tmp_path / "data").mkdir()
    monkeypatch.setattr("sys.frozen", True, raising=False)
    preparation = UpdatePreparation(tmp_path)
    started, finish = threading.Event(), threading.Event()

    def blocked(*_args):
        started.set()
        assert finish.wait(5)
        raise TimeoutError("blocked")

    with patch("homeplan.updates.prepare_update", side_effect=blocked) as download:
        preparation.start({"tag_name": "v9.0.0"})
        assert started.wait(2) and preparation.status == "downloading"
        preparation.start({"tag_name": "v9.0.0"})
        assert download.call_count == 1
        finish.set()
        import time

        for _ in range(100):
            if preparation.status == "skipped":
                break
            time.sleep(0.01)
        assert preparation.status == "skipped"


def test_prepared_app_failure_falls_back_to_original(tmp_path):
    app = tmp_path / "versions" / ("a" * 40) / "HomePlan"
    info = app / "_internal/homeplan/build-info.json"
    info.parent.mkdir(parents=True)
    info.write_text(json.dumps({"version": "9.0.0"}))
    (app / "HomePlan.exe").write_bytes(b"synthetic")
    (tmp_path / "data").mkdir()
    (tmp_path / "data/update-state.local.json").write_text(json.dumps({"build": "a" * 40}))
    with (
        patch("homeplan.gui_launcher.health", return_value=None),
        patch(
            "homeplan.updates.subprocess.run",
            side_effect=[subprocess.CompletedProcess([], 1), subprocess.CompletedProcess([], 0)],
        ) as run,
    ):
        _managed_launch(tmp_path)
    assert json.loads((tmp_path / "data/update-state.local.json").read_text())["failed"] is True
    assert run.call_count == 2
    assert run.call_args.args[0] == [str(tmp_path / "HomePlan.exe")]


def test_source_launcher_selects_matching_version_instead_of_old_server(tmp_path):
    from homeplan import __version__
    from homeplan.gui_launcher import ensure_server

    instance = hashlib.sha256(
        str((tmp_path / "data/homeplan.local.sqlite").resolve()).encode()
    ).hexdigest()[:16]
    statuses = {
        8765: {"service": "homeplan-gui", "instance": instance, "version": "0.5.0"},
        8766: {"service": "homeplan-gui", "instance": instance, "version": __version__},
    }
    with (
        patch("homeplan.gui_launcher.health", side_effect=lambda port: statuses.get(port)),
        patch("homeplan.gui_launcher.subprocess.Popen") as spawn,
    ):
        assert ensure_server(tmp_path) == "http://127.0.0.1:8766"
    spawn.assert_not_called()


def test_staged_update_is_available_even_when_github_is_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.frozen", True, raising=False)
    candidate = tmp_path / "candidate.exe"
    with patch("homeplan.updates.installed_update", return_value=candidate):
        preparation = UpdatePreparation(tmp_path)
        preparation.start(None)
    assert preparation.status == "ready"
