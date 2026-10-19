import hashlib
import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from homeplan.updates import ASSET, _managed_launch, fetch_release, release_url


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
        patch("homeplan.gui_launcher.health", return_value={"instance": instance}),
        patch("homeplan.gui_launcher.open_window") as open_window,
        patch("homeplan.updates.urllib.request.urlopen") as network,
    ):
        _managed_launch(tmp_path)
    open_window.assert_called_once_with("http://127.0.0.1:8765")
    network.assert_not_called()
