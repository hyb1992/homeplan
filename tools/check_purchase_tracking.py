"""Exercise contract progress, partial actual payments and persistence on synthetic plans."""

import json
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def check_standard(url: str, folder: Path) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge" if os.name == "nt" else None)
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url)
        expect(page.locator('[data-upgrade="advanced"]')).to_be_visible(timeout=120000)
        if page.locator("#modal").evaluate("node=>node.open"):
            page.locator("#modal-close").click()

        def api(path, body=None, method="GET"):
            return page.evaluate(
                """async ({path,body,method})=>{const response=await fetch(path,{method,headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});if(!response.ok)throw new Error(await response.text());return response.json();}""",
                {"path": path, "body": body, "method": method},
            )

        data = json.loads((ROOT / "tests/fixtures/synthetic_household.json").read_text("utf-8"))
        created = api(
            "/api/workspaces", {"label": "CONTRACT_SYNTHETIC_ONLY", "household": data}, "POST"
        )
        key = created["id"]
        baseline = api("/api/evaluate", {"household": created["household"]}, "POST")
        page.evaluate(
            "id=>localStorage.setItem(`homeplan-last-workspace:${location.origin}`,id)", key
        )
        page.goto(url + "#purchase")
        page.reload()
        expect(page.locator('[data-purchase="agreement"]')).to_be_visible(timeout=120000)
        page.locator('[data-purchase="agreement"]').click()
        page.locator("#tracking-start").select_option("본계약 완료")
        page.locator("#tracking-permit").uncheck()
        page.locator("#tracking-property").fill("계약한 우리집 · 가상")
        page.locator("#tracking-price").fill("5억원")
        page.locator("#tracking-deposit").fill("5000만원")
        page.locator("#tracking-interim").fill("1억원")
        page.locator('#tracking-form button[type="submit"]').click()
        expect(page.locator(".purchase-stats")).to_be_visible(timeout=30000)
        assert api(f"/api/workspaces/{key}")["household"].get("purchase_tracking") is None

        def payment(category, amount, *, invalid=False):
            page.locator('[data-purchase="payment-add"]').last.click()
            page.locator("#tracking-category").select_option(category)
            page.locator("#tracking-amount").fill(amount)
            if invalid:
                page.locator("#tracking-paid-date").fill("2099-01-01")
            page.locator('#tracking-form button[type="submit"]').click()
            if invalid:
                expect(page.locator("#tracking-error")).to_contain_text("오늘 이후")
                page.locator("#tracking-cancel").click()
            else:
                expect(page.locator("#tracking-form")).not_to_be_visible(timeout=30000)

        payment("계약금", "1000만원")
        payment("계약금", "4000만원")
        payment("중개보수", "200만원")
        expect(page.locator("#purchase-payments tbody tr")).to_have_count(3)
        expect(page.locator(".purchase-stats")).to_contain_text("5,200만")
        expect(page.locator(".purchase-stats")).to_contain_text("4억 5,000만")
        payment("잔금", "1만원", invalid=True)
        expect(page.locator("#purchase-payments tbody tr")).to_have_count(3)
        page.locator('[data-purchase="payment-edit"]').first.click()
        page.locator("#tracking-amount").fill("1500만원")
        page.locator('#tracking-form button[type="submit"]').click()
        expect(page.locator(".purchase-stats")).to_contain_text("5,700만", timeout=30000)
        page.locator('[data-purchase="payment-edit"]').first.click()
        page.locator("#tracking-amount").fill("1000만원")
        page.locator('#tracking-form button[type="submit"]').click()
        expect(page.locator(".purchase-stats")).to_contain_text("5,200만", timeout=30000)
        page.locator("#purchase-filter").select_option("중개보수")
        expect(page.locator("#purchase-payments tbody tr")).to_have_count(1)
        page.locator("#purchase-filter").select_option("전체")
        page.locator('[data-purchase="step-add"]').click()
        page.locator("#tracking-step-name").fill("열쇠 받기")
        page.locator("#tracking-status").select_option("진행 중")
        page.locator('#tracking-form button[type="submit"]').click()
        custom = page.locator(".purchase-milestone").filter(has_text="열쇠 받기")
        expect(custom).to_be_visible(timeout=30000)
        custom.locator('[data-purchase="step-delete"]').click()
        page.keyboard.press("Enter")
        expect(custom).to_have_count(0, timeout=30000)
        closing = page.locator(".purchase-milestone").filter(has_text="잔금 지급")
        closing.locator('[data-purchase="step-edit"]').click()
        page.locator("#tracking-status").select_option("완료")
        page.locator('#tracking-form button[type="submit"]').click()
        expect(closing).to_contain_text("완료", timeout=30000)
        page.locator("#save-button").click()
        expect(page.locator(".preview-changes")).to_contain_text("계약 진행·실제 지급 기록")
        page.get_by_role("button", name="확인하고 저장", exact=True).click()
        expect(page.locator("#save-state")).to_contain_text("저장된", timeout=30000)
        stored = api(f"/api/workspaces/{key}")
        tracking = stored["household"]["purchase_tracking"]
        assert tracking["price"] == 500000000 and len(tracking["payments"]) == 3
        dates = {row["name"]: row["planned_date"] for row in tracking["milestones"]}
        assert dates["중도금 지급"] == baseline["schedule"]["interim_date"]
        assert dates["입주"] == baseline["schedule"]["move_in_date"]
        after = api("/api/evaluate", {"household": stored["household"]}, "POST")
        assert after["purchase_progress"]["price_paid"] == 50000000
        assert after["purchase_progress"]["expenses_paid"] == 2000000
        assert (
            after["kpis"] == baseline["kpis"]
            and after["daily_balances"] == baseline["daily_balances"]
        )
        page.reload()
        expect(page.locator("#purchase-payments tbody tr")).to_have_count(3, timeout=120000)
        page.locator('[data-purchase="payment-delete"]').first.click()
        page.keyboard.press("Enter")
        expect(page.locator("#purchase-payments tbody tr")).to_have_count(2, timeout=30000)
        assert len(api(f"/api/workspaces/{key}")["household"]["purchase_tracking"]["payments"]) == 3
        page.on("dialog", lambda dialog: dialog.accept())
        page.reload()
        page.get_by_role("button", name="초안 복구", exact=True).click(timeout=30000)
        expect(page.locator("#purchase-payments tbody tr")).to_have_count(2, timeout=30000)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
        assert not errors, errors
        browser.close()


def check_permit(url: str, folder: Path) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge" if os.name == "nt" else None)
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url)
        expect(page.locator('[data-upgrade="advanced"]')).to_be_visible(timeout=120000)
        if page.locator("#modal").evaluate("node=>node.open"):
            page.locator("#modal-close").click()

        def api(path, body=None, method="GET"):
            return page.evaluate(
                """async ({path,body,method})=>{const r=await fetch(path,{method,headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});if(!r.ok)throw new Error(await r.text());return r.json();}""",
                {"path": path, "body": body, "method": method},
            )

        data = json.loads((ROOT / "tests/fixtures/synthetic_household.json").read_text("utf-8"))
        data["settings"]["land_permit_required"] = True
        created = api(
            "/api/workspaces", {"label": "PERMIT_SYNTHETIC_ONLY", "household": data}, "POST"
        )
        key = created["id"]
        baseline = api("/api/evaluate", {"household": created["household"]}, "POST")
        page.evaluate(
            "key=>localStorage.setItem(`homeplan-last-workspace:${location.origin}`,key)", key
        )
        page.goto(url + "#purchase")
        page.reload()
        page.locator('[data-purchase="agreement"]').click(timeout=120000)
        expect(page.locator("#tracking-start")).to_have_value("약정·허가 준비")
        expect(page.locator("#tracking-contract-date")).to_be_hidden()
        page.locator("#tracking-property").fill("허가 준비 중인 집 · 가상")
        for field, value in [
            ("price", "5억원"),
            ("deposit", "5000만원"),
            ("interim", "1억원"),
            ("reservation", "500만원"),
        ]:
            page.locator("#tracking-" + field).fill(value)
        page.locator('#tracking-form button[type="submit"]').click()
        expect(page.locator(".purchase-agreement")).to_contain_text("본계약 전", timeout=30000)
        expect(page.locator(".purchase-milestone")).to_have_count(8)
        assert page.locator(".purchase-milestone h3").all_text_contents()[:4] == [
            "약정금 지급",
            "토지거래허가 신청",
            "토지거래허가 승인",
            "본계약 체결",
        ]
        page.get_by_role("button", name="약정금 기록", exact=True).click()
        expect(page.locator("#tracking-category")).to_have_value("약정금")
        page.locator("#tracking-amount").fill("500만원")
        page.locator('#tracking-form button[type="submit"]').click()
        expect(page.locator(".purchase-stat").nth(2)).to_contain_text("4억 9,500만", timeout=30000)
        page.locator('[data-purchase="agreement"]').click()
        page.locator("#tracking-reservation-applied").uncheck()
        page.locator('#tracking-form button[type="submit"]').click()
        expect(page.locator(".purchase-stats")).to_contain_text(
            "정산 전 약정금 500만", timeout=30000
        )
        expect(page.locator(".purchase-stat").nth(2)).to_have_text("5억")
        page.locator('[data-purchase="agreement"]').click()
        page.locator("#tracking-reservation-applied").check()
        page.locator('#tracking-form button[type="submit"]').click()
        expect(page.locator(".purchase-milestone")).to_have_count(8, timeout=30000)
        for name in ["약정금 지급", "토지거래허가 신청", "토지거래허가 승인", "본계약 체결"]:
            row = page.locator(".purchase-milestone").filter(
                has=page.get_by_role("heading", name=name, exact=True)
            )
            row.locator('[data-purchase="step-edit"]').click()
            page.locator("#tracking-status").select_option("완료")
            page.locator('#tracking-form button[type="submit"]').click()
            expect(page.locator("#tracking-form")).not_to_be_visible(timeout=30000)
        expect(page.locator(".purchase-agreement")).not_to_contain_text("본계약 전")
        page.locator('[data-purchase="payment-add"]').last.click()
        expect(page.locator("#tracking-category")).to_have_value("계약금")
        page.locator("#tracking-amount").fill("4500만원")
        page.locator('#tracking-form button[type="submit"]').click()
        expect(page.locator(".purchase-stat").nth(2)).to_contain_text("4억 5,000만", timeout=30000)
        expect(page.locator("#purchase-payments tbody tr")).to_have_count(2)
        page.locator("#save-button").click()
        page.get_by_role("button", name="확인하고 저장", exact=True).click()
        expect(page.locator("#save-state")).to_contain_text("저장된", timeout=30000)
        stored = api(f"/api/workspaces/{key}")
        tracking = stored["household"]["purchase_tracking"]
        assert tracking["contract_date"] and tracking["permit_required"]
        assert tracking["reservation_amount"] == 5000000
        assert len({row["id"] for row in tracking["milestones"]}) == 8
        result = api("/api/evaluate", {"household": stored["household"]}, "POST")
        progress = result["purchase_progress"]
        assert progress["deposit_paid"] == 50000000 and progress["total_paid"] == 50000000
        assert progress["remaining_price"] == 450000000 and progress["completed_steps"] == 4
        assert (
            result["kpis"] == baseline["kpis"]
            and result["daily_balances"] == baseline["daily_balances"]
        )
        page.reload()
        expect(page.locator("#purchase-payments tbody tr")).to_have_count(2, timeout=120000)
        assert not errors, errors
        browser.close()


def check(url: str, folder: Path) -> None:
    check_standard(url, folder)
    check_permit(url, folder)


if __name__ == "__main__":
    from check_planning_menus import main

    main(checker=check)
