from datetime import date
from decimal import Decimal

import pytest

from homeplan.checks import evaluate
from homeplan.loans import loan_amounts
from homeplan.rules import acquisition_taxes, parental_benefit
from homeplan.storage import load_rules


def test_rule_loader_rejects_missing_metadata(tmp_path):
    (tmp_path / "bad.yaml").write_text("meta: {status: 미확정}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="메타데이터"):
        load_rules(tmp_path)


def test_tax_and_childcare_boundaries(rules):
    assert acquisition_taxes(rules, 610000000, 59.9)["rate"] == Decimal("0.0107")
    assert acquisition_taxes(rules, 1200000000, 85, True, "2027-03-01")["relief"] > 0
    assert acquisition_taxes(rules, 1200000001, 85, True, "2027-03-01")["relief"] == 0
    assert acquisition_taxes(rules, 1200000000, 85, True, "2029-01-01")["relief"] == 0
    assert parental_benefit(rules, 1, 5000000, True) == 2500000
    assert parental_benefit(rules, 3, 5000000) == 2500000
    assert parental_benefit(rules, 4, 5000000) == 2000000
    assert parental_benefit(rules, 7, 5000000) == 1600000


def test_ltv_always_caps_bank_quote(household, rules):
    resolved = household.resolved()
    listing = resolved.listing()
    listing.appraisal = 100000000
    loans = loan_amounts(resolved, listing, rules)
    assert loans["mortgage"] == 70000000
    assert loans["mortgage"] <= loans["mortgage_limit"]


def test_fixed_dates_stay_fixed_and_explicit_rate_survives_re_evaluation(household, rules):
    from homeplan.models import BankQuote

    household.bank_quotes = [
        BankQuote.model_validate(
            {
                "date": "2026-10-01",
                "bank": "가상은행",
                "options": [{"id": "q1", "method": "원리금균등", "rate": 0.05, "limit": 300000000}],
            }
        )
    ]
    household.settings.mortgage_quote_option = {"원리금균등": "q1"}
    h = household.resolved({"closing_date": "2027-03-01", "mortgage_rate": "0.045"})
    assert h.fund_events[1].available_date == date(2026, 12, 20)
    assert h.resolved().settings.mortgage_rate == Decimal("0.045")
    result = evaluate(h, None, rules, analyze_assumptions=False)
    assert result.kpis["mortgage_first_payment"] > 0
