"""Exercise the read-only customer perspective, its account switcher and print layout."""

from playwright.sync_api import Page, expect


def exercise_customer(page: Page, address: str) -> None:
    page.set_viewport_size({"width": 1366, "height": 900})
    page.goto(address)
    page.get_by_role("link", name="Customer preview", exact=True).click()
    expect(page.get_by_role("heading", name="Customer preview mode")).to_be_visible()
    examples = page.get_by_role("region", name="Prepared examples")
    examples.get_by_role("link", name="Bearing replenishment", exact=False).click()
    expect(page.locator(".quote-table")).to_contain_text("4 units outstanding")
    expect(page.locator(".quote-table")).to_contain_text("Delivery date unconfirmed")
    expect(page.locator(".totals")).to_contain_text("67.62")
    expect(page.locator(".document-terms")).to_contain_text("Stock is unreserved")
    page.get_by_role("link", name="Back to Kauri Engineering quotations").click()
    selector = page.get_by_label("Fictional account", exact=True)
    selector.focus()
    selector.select_option("Harbour Packaging")
    selector.press("Tab")
    expect(page.get_by_role("button", name="View account")).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", name="Harbour Packaging")).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    examples.get_by_role("link", name="Cylinder quotation", exact=False).click()
    expect(page.locator(".quote-table")).to_contain_text("137.50")
    expect(page.locator(".totals")).to_contain_text("316.25")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.set_viewport_size({"width": 320, "height": 640})
    assert page.locator("#quote-title").evaluate(
        "el => el.clientHeight < 1.5 * parseFloat(getComputedStyle(el).lineHeight)"
    ), "The quotation heading should fit on one line at 320px"
    page.emulate_media(media="print")
    expect(page.get_by_role("navigation", include_hidden=True)).to_be_hidden()
    expect(page.locator(".totals")).to_be_visible()
    pdf = page.pdf(format="A4", prefer_css_page_size=True)
    assert pdf.startswith(b"%PDF-")
    page.emulate_media(media="screen")
    page.get_by_role("link", name="Employee workspace").click()
