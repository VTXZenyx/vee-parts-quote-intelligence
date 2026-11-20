"""Follow the new employee guide using the same forms as the regular workflow."""

from playwright.sync_api import Page, expect


def exercise_guide(page: Page, address: str, width: int) -> None:
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(address)
    original_rows = page.locator(".inbox-table tbody tr").all_text_contents()
    page.get_by_role("button", name="Start product demonstration").press("Enter")
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
    page.get_by_role("link", name="Go to employee review").click()
    expect(page.locator(":target")).to_have_id("employee-action")
    page.get_by_role("button", name="Approve version 1").click()
    expect(page.locator("#guide")).to_contain_text("Guided demo complete")
    page.get_by_role("link", name="Open customer preview").press("Enter")
    expect(page.get_by_role("heading", name="VEE Industrial Supplies")).to_be_visible()
    expect(page.locator(".document-sheet")).to_contain_text("Delivery date unconfirmed")
    expect(page.locator(".totals")).to_contain_text("316.25")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.emulate_media(media="print")
    expect(page.get_by_role("link", name="Back to employee enquiry")).to_have_count(0)
    assert page.pdf(format="A4").startswith(b"%PDF")
    page.emulate_media(media="screen")
    page.get_by_role("link", name="Back to employee enquiry").click()
    page.locator("#guide").get_by_role("link", name="Inspect audit history").click()
    expect(page.locator(":target")).to_have_id("activity")
    expect(page.locator("#activity")).to_contain_text("Employee approved quotation version 1")
    page.get_by_role("button", name="Exit guide").click()
    expect(page.locator("#guide")).to_have_count(0)
    expect(page.locator("#quotation")).to_contain_text("Approved")
    page.get_by_role("button", name="Return to original workspace").click()
    assert page.locator(".inbox-table tbody tr").all_text_contents() == original_rows
    page.get_by_role("button", name="Start product demonstration").click()
    expect(page.locator("#guide")).to_contain_text("Receive the Harbour Packaging request")
    page.get_by_role("button", name="Return to original workspace").click()


def exercise_scenarios(page: Page, address: str) -> None:
    for scenario, sku, total in (
        ("bearings", "BRG-6205-2RS", "58.65"),
        ("conflict", "ADP-BSPP-14", ""),
        ("shortage", "BRG-6203-ZZ", "67.62"),
        ("contract", "CYL-32-100-DA", "316.25"),
    ):
        page.goto(address)
        page.get_by_label("Demonstration scenario").select_option(scenario)
        page.get_by_role("button", name="Start product demonstration").press("Enter")
        page.get_by_role("button", name="Receive test email").click()
        expect(page.locator("#guide")).to_be_visible()
        if scenario == "conflict":
            expect(page.locator("#request .issues")).to_contain_text("requested 350 bar, catalogue 250 bar")
            expect(page.get_by_role("button", name="Verify match")).to_have_count(0)
        else:
            page.get_by_role("checkbox", name=sku, exact=False).check()
            verify = "Verify for a partial quotation" if scenario == "shortage" else "Verify match"
            page.get_by_role("button", name=verify, exact=True).click()
            page.get_by_role("button", name="Create draft quotation").click()
            expect(page.locator(".totals")).to_contain_text(total)
            page.get_by_role("button", name="Approve version 1").click()
            if scenario == "shortage":
                expect(page.locator(".quote-table")).to_contain_text("4 units outstanding")
            if scenario == "contract":
                page.get_by_role("link", name="Receive revised order for three").click()
                page.get_by_role("button", name="Receive demo reply").click()
                expect(page.locator("#quotation")).to_contain_text("Historical")
                page.get_by_label("Reason for replacing the previous requirements").fill("Buyer confirmed three cylinders.")
                page.get_by_role("button", name="Confirm revised request").click()
                page.get_by_role("checkbox", name=sku, exact=False).check()
                page.get_by_role("button", name="Verify match", exact=True).click()
                page.get_by_role("button", name="Create draft quotation").click()
                expect(page.locator(".totals")).to_contain_text("474.38")
                page.get_by_role("button", name="Approve version 2").click()
                expect(page.locator(".versions")).to_contain_text("316.25")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.get_by_role("button", name="Return to original workspace").click()
