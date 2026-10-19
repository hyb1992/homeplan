"""가상 입력으로 자금 빌더·추천·도넛·저장·모바일을 검증한다."""

import json
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def check(url: str, folder: Path) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge" if os.name == "nt" else None)
        context = browser.new_context(viewport={"width": 1440, "height": 1050})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url)
        expect(page.locator('[data-upgrade="advanced"]')).to_be_visible(timeout=120000)
        if page.locator("#modal").evaluate("e=>e.open"):
            page.locator("#modal-close").click()
        data = json.loads((ROOT / "tests/fixtures/synthetic_household.json").read_text("utf-8"))
        data["fund_events"] = [
            {
                "id": "CASH",
                "name": "기존 예금",
                "type": "현금·예금",
                "value": 100000000,
                "status": "확정",
            },
            {
                "id": "LEASE",
                "name": "보증금",
                "type": "전세보증금",
                "value": 200000000,
                "available_date": "퇴거일",
                "use_for_purchase": False,
            },
            {
                "id": "STOCK",
                "name": "주식",
                "type": "투자자산",
                "value": 20000000,
                "cash_out_amount": 18000000,
                "cost": 1000000,
            },
            {
                "id": "REFUND",
                "name": "연말정산 환급",
                "type": "성과급·환급금",
                "value": 3000000,
                "available_date": "잔금일",
            },
            {
                "id": "DEBT",
                "name": "전세대출",
                "type": "기존 전세대출(부채)",
                "value": 50000000,
                "available_date": "전세대출상환일",
            },
            {
                "id": "OFF",
                "name": "제외한 예금",
                "type": "현금·예금",
                "value": 1000000000,
                "status": "제외",
            },
        ]
        key = page.evaluate(
            """async h=>{
            const response=await fetch('/api/workspaces',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({label:'FUND_BUILDER_SYNTHETIC',household:h})});
            const saved=await response.json();localStorage.setItem(`homeplan-last-workspace:${location.origin}`,saved.id);return saved.id;
        }""",
            data,
        )
        page.reload()
        expect(page.locator(".runtime-summary")).to_be_visible(timeout=120000)
        page.locator('a[href="#funds"]:visible').first.click()
        expect(page.locator(".fund-donut-total")).to_have_attribute("data-total", "320000000")
        page.locator('[data-action="fund-add"]').first.click()
        expect(page.locator(".fund-builder-progress")).to_be_visible()
        page.locator(".builder-expand").click()
        expect(page.locator(".fund-type-choice")).to_have_count(9)
        page.locator(".builder-expand").click()
        page.locator("#record-name").fill("목돈")
        page.locator("#builder-next").click()
        expect(page.locator("#record-form .modal-error")).to_contain_text("유형을 선택")
        page.locator("#record-name").fill("연말정산 환급")
        expect(page.locator("#record-type")).to_have_value("성과급·환급금")
        page.locator('[data-builder-type="투자자산"]').click()
        page.locator("#record-name").fill("남편 예금")
        expect(page.locator("#record-type")).to_have_value("투자자산")
        page.locator("#record-name").press("Enter")
        expect(page.locator('.fund-builder-step[data-step="1"]')).to_be_visible()
        page.locator("#record-value").fill("50만원")
        page.locator("#record-cost").fill("1만원")
        page.locator("#builder-back").click()
        page.locator("#record-name").press("Enter")
        expect(page.locator("#record-value")).not_to_have_value("")
        page.locator("#builder-next").click()
        expect(page.locator(".fund-builder-review")).to_contain_text("490,000원")
        page.locator("#record-owner").select_option("남편")
        page.locator('[name="use_for_purchase"]').uncheck()
        page.locator("#record-available_date").fill("틀린 날짜")
        page.locator('#record-form button[type="submit"]').click()
        expect(page.locator("#record-form .modal-error")).not_to_be_empty()
        expect(page.locator(".fund-donut-total")).to_have_attribute("data-total", "320000000")
        expect(page.locator("#record-form")).to_be_visible()
        page.locator("#record-available_date").fill("지금")
        page.locator("#record-status").select_option("확정")
        page.locator('#record-form button[type="submit"]').click()
        expect(page.locator("#record-form")).not_to_be_visible()
        expect(page.locator(".fund-donut-total")).to_have_attribute("data-total", "320490000")
        page.locator('[data-action="fund-add"]').first.click()
        page.locator("#record-name").fill("청년도약계좌 적금")
        expect(page.locator("#record-type")).to_have_value("적금·청년도약계좌")
        page.locator("#builder-next").click()
        page.locator("#record-is_variable").check()
        page.locator("#record-conservative_amount").fill("300만원")
        page.locator("#record-aggressive_amount").fill("200만원")
        page.locator("#builder-next").click()
        expect(page.locator('.fund-builder-step[data-step="1"]')).to_be_visible()
        expect(page.locator("#record-form .modal-error")).to_contain_text("보수적 금액")
        page.locator("#record-aggressive_amount").fill("600만원")
        page.locator("#builder-next").click()
        page.locator("#record-available_date").fill("잔금일")
        page.locator('#record-form button[type="submit"]').click()
        expect(page.locator("#record-form")).not_to_be_visible()
        expect(page.locator(".fund-donut-total")).to_have_attribute("data-total", "323490000")
        page.locator("#variable-asset-mode").select_option("공격적")
        expect(page.locator(".fund-donut-total")).to_have_attribute("data-total", "326490000")
        savings_row = page.locator("#fund-list tbody tr").filter(has_text="청년도약계좌 적금")
        savings_row.locator('[data-action="fund-toggle"]').click()
        expect(page.locator(".fund-donut-total")).to_have_attribute("data-total", "320490000")
        savings_row.locator('[data-action="fund-toggle"]').click()
        expect(page.locator(".fund-donut-total")).to_have_attribute("data-total", "326490000")
        page.locator("#fund-purchase-only").check()
        expect(page.locator(".fund-donut-total")).to_have_attribute("data-total", "126000000")
        page.locator('[data-fund-scope="owned"]').click()
        expect(page.locator(".fund-donut-total")).to_have_attribute("data-total", "123000000")
        page.locator('.fund-chart-row[data-fund-filter="적금·청년도약계좌"]').press("Enter")
        expect(page.locator("#fund-type-filter")).to_have_value("적금·청년도약계좌")
        expect(page.locator("#fund-list tbody tr")).to_have_count(1)
        page.locator("#fund-filter-clear").click()
        expect(page.locator("#fund-list tbody tr")).to_have_count(8)
        page.locator('[data-fund-scope="incoming"]').click()
        expect(page.locator(".fund-donut-total")).to_have_attribute("data-total", "3000000")
        page.locator('[data-action="fund-edit"][data-id="CASH"]').click()
        expect(page.locator(".fund-builder-progress")).to_have_count(0)
        page.locator("#record-cancel").click()
        page.locator("#save-button").click()
        page.get_by_role("button", name="확인하고 저장", exact=True).click()
        expect(page.locator("#save-state")).to_have_text("저장된 계획")
        saved = page.evaluate("async key=>(await fetch(`/api/workspaces/${key}`)).json()", key)
        added = next(r for r in saved["household"]["fund_events"] if r["name"] == "남편 예금")
        assert added["type"] == "투자자산" and added["value"] == 500000 and added["cost"] == 10000
        assert added["use_for_purchase"] is False and added["available_date"] == "지금"
        page.reload()
        expect(page.locator(".fund-donut-total")).to_have_attribute(
            "data-total", "326490000", timeout=120000
        )
        page.screenshot(path=ROOT / "data/fund-composition.local.png")
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth")
        page.locator('[data-action="fund-add"]').first.click()
        page.locator("#record-name").fill("퇴직금")
        expect(page.locator("#record-type")).to_have_value("퇴직 관련 수령금")
        assert page.locator("#modal").evaluate("e=>e.scrollWidth<=e.clientWidth")
        page.screenshot(path=ROOT / "data/fund-builder-mobile.local.png")
        page.locator("#builder-next").click()
        page.locator("#record-value").fill("1000만원")
        page.locator("#builder-next").click()
        page.locator('[data-fund-timing="closing"]').click()
        expect(page.locator("#record-available_date")).to_have_value("잔금일")
        page.locator("#record-cancel").click()
        # Cancel and a failed final validation do not leave hidden extra rows.
        assert (
            page.evaluate("async key=>(await fetch(`/api/workspaces/${key}`)).json()", key) == saved
        )
        data["fund_events"] = []
        page.evaluate(
            """async h=>{const r=await fetch('/api/workspaces',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({label:'EMPTY_FUNDS',household:h})});const p=await r.json();localStorage.setItem(`homeplan-last-workspace:${location.origin}`,p.id);} """,
            data,
        )
        page.reload()
        expect(page.locator(".fund-chart-empty")).to_be_visible(timeout=120000)
        expect(page.locator(".fund-segment")).to_have_count(0)
        assert not errors, errors
        browser.close()


if __name__ == "__main__":
    from check_planning_menus import main

    main(check)
