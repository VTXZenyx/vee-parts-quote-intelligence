"""Follow the new employee guide using the same forms as the regular workflow."""

from playwright.sync_api import Page, expect


def exercise_guide(page: Page, address: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(address)
    original_rows = page.locator(".inbox-table tbody tr").all_text_contents()
    page.get_by_role("button", name="Start guided demo").press("Enter")
    expect(page.locator("#guide")).to_contain_text("Harbour Packaging")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.get_by_role("button", name="Receive test email").click()
    expect(page.locator("#guide")).to_contain_text("missing")
    expect(page.locator("#evidence")).to_contain_text("Outstanding issues")
    expect(page.get_by_role("button", name="Create draft quotation")).to_have_count(0)
    page.get_by_role("button", name="Approve clarification").click()
    page.locator("#guide").get_by_role("link", name="Load the cylinder reply").click()
    expect(page.get_by_label("Message", exact=True)).to_have_value(
        "Bore 32 mm, stroke 100 mm, double acting, ISO 15552, G1/8 ports, foot mount."
    )
    page.get_by_role("button", name="Receive demo reply").click()
    page.get_by_role("checkbox", name="Confirm CYL-32-100-DA").check()
    page.get_by_role("button", name="Verify match", exact=True).click()
    page.get_by_role("button", name="Create draft quotation").click()
    expect(page.locator("#quotation")).to_contain_text("316.25")
    expect(page.locator("#quotation")).to_contain_text("41.25")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.get_by_role("button", name="Approve version 1").click()
    expect(page.locator("#guide")).to_contain_text("Guided demo complete")
    page.locator("#guide").get_by_role("link", name="Inspect audit history").click()
    expect(page.locator(":target")).to_have_id("activity")
    expect(page.locator("#activity")).to_contain_text("Employee approved quotation version 1")
    page.get_by_role("button", name="Exit guide").click()
    expect(page.locator("#guide")).to_have_count(0)
    expect(page.locator("#quotation")).to_contain_text("Approved")
    page.get_by_role("button", name="Return to original workspace").click()
    assert page.locator(".inbox-table tbody tr").all_text_contents() == original_rows
    page.get_by_role("button", name="Start guided demo").click()
    expect(page.locator("#guide")).to_contain_text("Receive the Harbour Packaging request")
    page.get_by_role("button", name="Return to original workspace").click()
