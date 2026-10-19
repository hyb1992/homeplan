import json
from unittest.mock import MagicMock, patch

from homeplan.gui_launcher import browser_profile, ensure_server
from homeplan.repository import Repository, seed_repository


def test_app_browser_profile_disables_autofill_without_changing_other_profiles(tmp_path):
    ordinary = tmp_path / "ordinary-browser/Default/Preferences"
    ordinary.parent.mkdir(parents=True)
    original = b'{"autofill":{"profile_enabled":true},"existing":"keep"}'
    ordinary.write_bytes(original)
    profile = browser_profile(tmp_path / "app", "edge")
    assert profile == tmp_path / "app/data/edge.local.profile"
    preferences = json.loads((profile / "Default/Preferences").read_text(encoding="utf-8"))
    assert preferences["autofill"]["profile_enabled"] is False
    assert preferences["autofill"]["credit_card_enabled"] is False
    assert preferences["profile"]["password_manager_enabled"] is False
    assert ordinary.read_bytes() == original


def test_reopening_app_does_not_overwrite_live_browser_preferences(tmp_path):
    profile = browser_profile(tmp_path, "edge")
    preferences = profile / "Default/Preferences"
    original = preferences.read_bytes() + b"\n"
    preferences.write_bytes(original)
    assert browser_profile(tmp_path, "edge") == profile
    assert preferences.read_bytes() == original


def test_fresh_distribution_only_creates_zero_plan_on_first_launch(tmp_path, household):
    (tmp_path / "data").mkdir()
    (tmp_path / "data/demo.local.json").write_text(household.model_dump_json(), encoding="utf-8")
    (tmp_path / "fresh-start.flag").touch()
    repo = Repository(tmp_path / "data/homeplan.local.sqlite")
    seed_repository(repo, tmp_path)
    stored = repo.get("actual")
    assert stored["household"]["fund_events"] == []
    assert stored["household"]["parent_support"] == []
    assert stored["household"]["loan_prepayments"] == []
    assert stored["household"]["listings"][0]["price"] == 0
    assert stored["household"]["settings"]["start_today"]
    assert stored["household"]["onboarding_pending"]
    stored["household"]["settings"]["husband_net_pay"] = 1230000
    repo.save("actual", stored["household"], stored["revision"])
    seed_repository(repo, tmp_path)
    assert repo.get("actual")["household"]["settings"]["husband_net_pay"] == 1230000


def test_frozen_app_launches_itself_as_server(tmp_path):
    import hashlib

    instance = hashlib.sha256(
        str((tmp_path / "data/homeplan.local.sqlite").resolve()).encode()
    ).hexdigest()[:16]
    process = MagicMock()
    with (
        patch("homeplan.gui_launcher.sys.frozen", True, create=True),
        patch("homeplan.gui_launcher.sys.executable", "HomePlan.exe"),
        patch("homeplan.gui_launcher.health", side_effect=[None, {"instance": instance}]),
        patch("homeplan.gui_launcher.socket.socket"),
        patch("homeplan.gui_launcher.subprocess.Popen", return_value=process) as launch,
    ):
        assert ensure_server(tmp_path) == "http://127.0.0.1:8765"
        assert launch.call_args.args[0] == ["HomePlan.exe", "--serve", "--port", "8765"]
