"""Exercise the live Flask UI on a fresh disposable database using local Chromium."""

import shutil
import tempfile
from pathlib import Path
from threading import Thread

from playwright.sync_api import Page, expect, sync_playwright
from werkzeug.serving import make_server

from scripts.browser_catalogue import exercise_catalogue
from scripts.browser_customer import exercise_customer
from scripts.browser_dashboard import exercise_dashboard
from scripts.browser_demo import exercise_demo
from scripts.browser_guide import exercise_guide, exercise_scenarios
from scripts.browser_providers import exercise_providers
from scripts.browser_records import verify_scenario_records
from scripts.browser_review import exercise_review
from vee import store
from vee.web import create_app


def click_action(page: Page, name: str) -> None:
    page.locator(f'button[name="action"][value="{name}"]').click()


def exercise(page: Page, address: str) -> None:
    page.goto(address)
    page.get_by_role("link", name="New enquiry").click()
    page.get_by_label("Customer account").select_option("Kauri Engineering")
    page.get_by_label("Enquiry subject").fill("Bearing quotation")
    page.get_by_label("Original request").fill("Please quote 4 x BRG-6205-2RS.")
    page.get_by_role("button", name="Save enquiry").click()
    expect(page.get_by_role("heading", name="Bearing quotation")).to_be_visible()
    expect(page.get_by_role("button", name="Confirm product", exact=True)).to_be_visible()
    page.get_by_role("checkbox", name="Confirm BRG-6205-2RS").check()
    click_action(page, "verify_match")
    click_action(page, "create_quote")
    page.locator("details.edit summary").first.click()
    page.get_by_label("Quantity · BRG-6205-2RS").fill("6")
    click_action(page, "edit_quote")
    expect(page.locator(".action-column")).to_contain_text("BRG-6205-2RS (requested 4, quoted 6)")
    expect(page.locator('[value="approve_quote"]')).to_have_count(0)
    click_action(page, "request_quantity_confirmation")
    page.locator('textarea[name="body"]').fill("Revised request: 6 x BRG-6205-2RS.")
    click_action(page, "simulate_reply")
    page.locator("#reconcile-reason").fill("The customer confirmed the complete updated request.")
    click_action(page, "reconcile_requirements")
    expect(page.locator('[value="create_quote"]')).to_have_count(0)
    page.get_by_role("checkbox", name="Confirm BRG-6205-2RS").check()
    click_action(page, "verify_match")
    click_action(page, "create_quote")
    click_action(page, "approve_quote")
    case_url = page.url
    assert page.goto(case_url + "/customer-preview?version=2").status == 409
    assert page.goto(case_url + "/customer-preview?version=3").status == 200
    expect(page.locator(".quote-table .requested-quantity")).to_contain_text("6")
    expect(page.locator(".quote-table .quoted-quantity")).to_contain_text("6")
    page.goto(address + "/enquiries/ENQ-1037")
    page.get_by_text("inspection-fitting.webp", exact=True).click()
    picture = page.get_by_role("img", name="Synthetic inspection photo", exact=False)
    expect(picture).to_be_visible()
    assert picture.evaluate("el => el.complete && el.naturalWidth > 0")
    page.goto(address)
    search = page.get_by_role("searchbox")
    search.fill("Harbour")
    search.press("Enter")
    expect(page.locator("tbody tr")).to_have_count(1)
    link = page.locator('a[href="/enquiries/ENQ-1042"]').first
    expect(link).to_be_visible()
    link.click()
    for action in ("approve_clarification", "simulate_reply", "verify_match", "create_quote"):
        if action == "verify_match":
            page.get_by_role("checkbox", name="Confirm CYL-32-100-DA").check()
        click_action(page, action)
    expect(page.get_by_text("316.25", exact=False).first).to_be_visible()
    editor = page.get_by_text("Edit quotation", exact=True)
    editor.click()
    page.locator('[name="quantity_CYL-32-100-DA"]').fill("4")
    editor.click()
    expect(page.locator('[value="approve_quote"]')).to_be_disabled()
    editor.click()
    page.locator('[name="quantity_CYL-32-100-DA"]').fill("2")
    editor.click()
    expect(page.locator('[value="approve_quote"]')).to_be_enabled()
    editor.click()
    page.locator('[name="quantity_CYL-32-100-DA"]').fill("4")
    page.get_by_role("button", name="Discard edits").click()
    editor.click()
    expect(page.locator('[value="approve_quote"]')).to_be_enabled()
    page.get_by_text("Reject this quotation", exact=True).click()
    page.locator("#reason-reject_quote").fill("Please quote one cylinder for now.")
    click_action(page, "reject_quote")
    expect(page.locator("#quotation .rejection-note")).to_contain_text("Please quote one cylinder for now.")
    page.locator('[name="quantity_CYL-32-100-DA"]').fill("1")
    click_action(page, "edit_quote")
    expect(page.get_by_text("158.13", exact=False).first).to_be_visible()
    click_action(page, "approve_quote")
    page.reload()
    expect(page.get_by_text("Approved", exact=True).first).to_be_visible()
    page.emulate_media(media="print")
    expect(page.locator("#quotation")).to_be_visible()
    expect(page.locator("#quotation")).to_contain_text("158.13")
    page.emulate_media(media="screen")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.goto(address)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "smoke.sqlite3"
        demos = database.with_name(database.name + ".demos")
        server = make_server("127.0.0.1", 0, create_app(database))
        worker = Thread(target=server.serve_forever)
        worker.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=shutil.which("chromium"))
                context = browser.new_context(viewport={"width": 1366, "height": 900})
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("response", lambda r: errors.append(f"{r.status} {r.url}")
                        if r.status >= 400 and "/static/" in r.url else None)
                address = f"http://127.0.0.1:{server.server_port}"
                exercise_dashboard(page, address)
                exercise(page, address)
                exercise_review(page, address)
                exercise_demo(page, address)
                exercise_providers(page, address)
                original = store.inbox(database)
                prior = set(demos.glob("*.sqlite3"))
                exercise_guide(page, address, 1366)
                exercise_guide(page, address, 390)
                exercise_scenarios(page, address)
                verify_scenario_records(set(demos.glob("*.sqlite3")) - prior)
                assert store.inbox(database) == original
                exercise_customer(page, address)
                exercise_catalogue(page, address)
                assert store.inbox(database) == original
                assert not errors, errors
                browser.close()
            print("Browser workflow and mobile layout checks passed.")
        finally:
            server.shutdown()
            worker.join()
            server.server_close()


if __name__ == "__main__":
    main()
