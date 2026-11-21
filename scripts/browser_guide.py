"""Drive each guided customer case using ordinary employee controls."""

from playwright.sync_api import Page, expect


def start_scenario(page: Page, address: str, scenario: str) -> None:
    page.goto(address)
    page.get_by_role("link", name="Try a demo").press("Enter")
    choices = page.get_by_role("group", name="Demonstration scenario")
    expect(choices.get_by_role("radio")).to_have_count(5)
    choices.get_by_role("radio", name=scenario).check()
    page.get_by_role("button", name="Start scenario").press("Enter")
    expect(page.locator("#guide h2")).to_have_text(scenario)
    expect(page.locator("[aria-current=step]")).to_have_text("Request")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.get_by_role("button", name="Open enquiry").press("Enter")
    expect(page.locator("[aria-current=step]")).to_have_text("Product review")


def expect_decision(page: Page, label: str) -> None:
    controls = page.locator("#employee-action .button.primary:visible")
    expect(controls).to_have_count(1)
    expect(controls).to_have_text(label)


def exercise_guide(page: Page, address: str, width: int) -> None:
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(address)
    original_rows = page.locator(".inbox-table tbody tr").all_text_contents()
    start_scenario(page, address, "Missing product information")
    expect(page.locator("#request .issues")).to_contain_text("bore")
    expect(page.get_by_role("button", name="Create quote")).to_have_count(0)
    expect_decision(page, "Approve question")
    page.get_by_role("button", name="Approve question").press("Enter")
    expect_decision(page, "Add customer reply")
    expect(page.locator("#employee-action .prepared-message")).to_contain_text("Bore 32 mm, stroke 100 mm")
    page.get_by_role("button", name="Add customer reply").press("Enter")
    expect(page.locator("#conversation li")).to_have_count(3)
    expect_decision(page, "Confirm product")
    page.get_by_role("checkbox", name="Confirm CYL-32-100-DA").press("Space")
    page.get_by_role("button", name="Confirm product", exact=True).press("Enter")
    expect(page.locator("[aria-current=step]")).to_have_text("Prepare quote")
    page.get_by_role("button", name="Create quote").press("Enter")
    expect(page.locator("#quotation")).to_contain_text("316.25")
    expect(page.locator("#quotation")).to_contain_text("41.25")
    expect(page.locator("[aria-current=step]")).to_have_text("Approval")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.get_by_role("link", name="Go to employee review").press("Enter")
    expect(page.locator(":target")).to_have_id("employee-action")
    page.get_by_role("button", name="Approve version 1").press("Enter")
    expect(page.locator("[aria-current=step]")).to_have_text("Preview")
    page.get_by_role("link", name="View customer quote").press("Enter")
    expect(page.get_by_role("heading", name="VEE Industrial Supplies")).to_be_visible()
    expect(page.locator(".document-sheet")).to_contain_text("Delivery date unconfirmed")
    expect(page.locator(".totals")).to_contain_text("316.25")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.emulate_media(media="print")
    expect(page.get_by_role("link", name="Back to employee enquiry")).to_have_count(0)
    assert page.pdf(format="A4").startswith(b"%PDF")
    page.emulate_media(media="screen")
    page.get_by_role("link", name="Back to employee enquiry").click()
    page.get_by_role("link", name="Inspect audit history").click()
    expect(page.locator("#activity")).to_be_visible()
    expect(page.locator("#activity")).to_contain_text("Employee approved quotation version 1")
    page.get_by_text("Demo controls", exact=True).press("Enter")
    page.get_by_role("button", name="Restart in fresh workspace").press("Enter")
    expect(page.locator("[aria-current=step]")).to_have_text("Request")
    page.get_by_text("Demo controls", exact=True).press("Enter")
    page.get_by_role("button", name="Exit guide").press("Enter")
    expect(page.locator("#guide")).to_have_count(0)
    page.get_by_role("button", name="Return to original workspace").click()
    assert page.locator(".inbox-table tbody tr").all_text_contents() == original_rows


def exercise_scenarios(page: Page, address: str) -> None:
    page.goto(address)
    original_rows = page.locator(".inbox-table tbody tr").all_text_contents()
    for scenario, sku, total in (
        ("Simple parts quotation", "BRG-6205-2RS", "58.65"),
        ("Incompatible product", "ADP-BSPP-14", ""),
        ("Not enough stock", "BRG-6203-ZZ", "67.62"),
        ("Customer changes an order", "CYL-32-100-DA", "316.25"),
    ):
        start_scenario(page, address, scenario)
        if scenario == "Incompatible product":
            expect(page.locator("#request .issues")).to_contain_text("requested 350 bar, catalogue 250 bar")
            expect(page.get_by_role("button", name="Confirm product")).to_have_count(0)
            # An incompatible request is complete as a demo when the unsafe quotation is blocked.
            expect(page.locator("#quotation")).to_have_count(0)
            page.get_by_text("Audit history ·", exact=False).first.click()
            expect(page.locator("#activity")).to_be_visible()
        else:
            page.get_by_role("checkbox", name=sku, exact=False).check()
            verify = "Confirm partial supply" if scenario == "Not enough stock" else "Confirm product"
            expect_decision(page, verify)
            page.get_by_role("button", name=verify, exact=True).click()
            page.get_by_role("button", name="Create quote").click()
            expect(page.locator(".totals")).to_contain_text(total)
            page.get_by_role("button", name="Approve version 1").click()
            if scenario == "Not enough stock":
                expect(page.locator(".quote-table")).to_contain_text("4 units outstanding")
            if scenario == "Customer changes an order":
                expect_decision(page, "Add revised request")
                page.get_by_role("button", name="Add revised request").click()
                expect(page.locator("#quotation")).to_contain_text("Historical")
                expect_decision(page, "Confirm updated request")
                page.get_by_label("Why does this replace the earlier request?").fill("Buyer confirmed three cylinders.")
                page.get_by_role("button", name="Confirm updated request").click()
                page.get_by_role("checkbox", name=sku, exact=False).check()
                page.get_by_role("button", name="Confirm product", exact=True).click()
                page.get_by_role("button", name="Create quote").click()
                total = "474.38"
                expect(page.locator(".totals")).to_contain_text(total)
                page.get_by_role("button", name="Approve version 2").click()
                expect(page.locator(".versions")).to_contain_text("316.25")
            page.get_by_role("link", name="View customer quote").click()
            expect(page.locator(".document-sheet .totals")).to_contain_text(total)
            page.get_by_role("link", name="Back to employee enquiry").click()
            page.get_by_role("link", name="Inspect audit history").click()
            expect(page.locator("#activity")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.get_by_role("button", name="Return to original workspace").click()
        assert page.locator(".inbox-table tbody tr").all_text_contents() == original_rows
