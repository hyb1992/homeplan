from pathlib import Path

import pytest

from homeplan.storage import load_household, load_rules

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def household():
    return load_household(ROOT / "tests/fixtures/synthetic_household.json")


@pytest.fixture
def rules():
    return load_rules(ROOT / "data/rules")
