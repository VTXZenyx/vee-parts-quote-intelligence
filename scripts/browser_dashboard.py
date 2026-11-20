"""Verify dashboard counts, staged search and keyboard navigation."""

from playwright.sync_api import Page, expect


def exercise_dashboard(page: Page, address: str) -> None:
    page.goto(address)
    expect(page.get_by_role("heading", name="Enquiry workspace")).to_be_visible()
    page.keyboard.press("Tab")
    expect(page.get_by_role("link", name="Skip to content")).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.locator("#main")).to_be_focused()
    blockers = page.get_by_role("link", name="Blocked 4")
    expect(blockers).to_be_visible()
    blockers.focus()
    page.keyboard.press("Enter")
    expect(page.locator(".inbox-table tbody tr")).to_have_count(4)
    search = page.get_by_role("searchbox")
    search.fill("Coastal")
    search.press("Enter")
    expect(page.locator(".inbox-table tbody tr")).to_have_count(2)
    expect(blockers).to_have_attribute("aria-current", "true")
    page.get_by_role("link", name="Clear filters").click()
    expect(page.locator(".inbox-table tbody tr")).to_have_count(6)
    response = page.goto(address + "/enquiries/unknown")
    assert response is not None and response.status == 404
    expect(page.get_by_role("heading", name="Page unavailable")).to_be_visible()
    page.get_by_role("link", name="Enquiry inbox", exact=True).press("Enter")
    expect(page.locator(".inbox-table tbody tr")).to_have_count(6)
