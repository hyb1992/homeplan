"""Exercise contract progress, partial actual payments and persistence on synthetic plans."""

import json
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def check(url: str, folder: Path) -> None:
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


if __name__ == "__main__":
    from check_planning_menus import main

    main(checker=check)
