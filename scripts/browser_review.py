"""Employee review scenarios that complement the primary enquiry browser workflow."""

from playwright.sync_api import Page, expect


def clarification_and_reconciliation(page: Page, address: str) -> None:
    page.goto(address + "/enquiries/ENQ-1041")
    page.get_by_text("Reject proposed match", exact=True).click()
    page.get_by_label("Reason for rejection").fill("Confirm the complete customer request.")
    page.get_by_role("button", name="Record rejection").click()
    draft = page.get_by_label("Question for the customer")
    expect(draft).to_have_value("")

    with page.context.new_page() as earlier:
        earlier.goto(page.url)
        draft.fill("Which bearing reference and quantity do you need?")
        page.get_by_role("button", name="Save draft").click()
        earlier.get_by_label("Question for the customer").fill("Earlier tab's edit")
        earlier.get_by_role("button", name="Save draft").click()
        expect(earlier.get_by_role("alert")).to_contain_text("enquiry has changed")
        expect(earlier.get_by_label("Question for the customer")).to_have_value(
            "Which bearing reference and quantity do you need?"
        )

    page.get_by_text("Reject question draft", exact=True).click()
    page.get_by_label("Reason for rejection").fill("Ask for the complete revised request.")
    page.get_by_role("button", name="Record rejection").click()
    expect(draft).to_have_value("")
    expect(page.locator("#conversation li")).to_have_count(1)
    draft.fill("Please provide the complete revised order.")
    page.get_by_role("button", name="Approve question").click()
    page.get_by_label("Customer reply").fill("Revised request: 2 x BLT-M12-80.")
    page.get_by_role("button", name="Add customer reply").click()
    page.get_by_label("Why does this replace the earlier request?").fill(
        "The customer explicitly replaced the original order."
    )
    page.get_by_role("button", name="Confirm updated request").click()
    expect(page.locator("#request")).to_contain_text("4 x BRG-6205-2RS")
    expect(page.locator("#conversation")).to_contain_text("2 x BLT-M12-80")
    expect(page.locator("#activity")).to_contain_text("explicitly replaced the original order")
    page.get_by_role("checkbox", name="Confirm BLT-M12-80").check()
    page.get_by_role("button", name="Confirm product", exact=True).click()
    page.get_by_role("button", name="Create quote").click()
    expect(page.locator("#quotation")).to_contain_text("BLT-M12-80")

    page.get_by_text("Recheck stock, price and specifications", exact=True).click()
    page.get_by_role("button", name="Check latest product details", exact=True).click()
    expect(page.locator("#quotation")).to_contain_text("Historical")
    expect(page.get_by_role("button", name="Approve version 1")).to_have_count(0)
    page.get_by_role("checkbox", name="Confirm BLT-M12-80").check()
    page.get_by_role("button", name="Confirm product", exact=True).click()
    page.get_by_role("button", name="Create quote").click()
    expect(page.get_by_role("button", name="Approve version 2")).to_be_visible()
    page.get_by_text("Previous versions (1)", exact=True).click()
    expect(page.locator(".versions")).to_contain_text("Version 1")


def multi_line_quote_and_print(page: Page, address: str) -> None:
    page.goto(address + "/enquiries/ENQ-1040")
    page.get_by_role("checkbox", name="Confirm BRG-6205-2RS").check()
    page.get_by_role("button", name="Confirm products").click()
    expect(page.get_by_role("checkbox", name="Confirm BLT-M12-80")).not_to_be_checked()
    expect(page.get_by_role("button", name="Create quote")).to_have_count(0)
    page.get_by_role("checkbox", name="Confirm BLT-M12-80").check()
    page.get_by_role("button", name="Confirm products").click()
    page.get_by_role("button", name="Create quote").click()
    expect(page.locator(".quote-table tbody tr")).to_have_count(2)
    page.get_by_text("Edit quotation", exact=True).click()
    page.get_by_label("Quantity · BRG-6205-2RS").fill("1")
    page.get_by_label("Quotation notes").fill("Supply the first bearing now.")
    page.get_by_role("button", name="Save new version").click()
    bearing = page.locator(".quote-table tbody tr").filter(has_text="BRG-6205-2RS")
    expect(bearing.locator(".requested-quantity")).to_have_text("Requested2")
    expect(bearing.locator(".quoted-quantity")).to_have_text("Quoted1")
    page.get_by_role("button", name="Approve version 2").click()

    # Verify the real button binding without opening an interactive system dialog.
    page.evaluate("window.print = () => window.dispatchEvent(new Event('print-request'))")
    page.evaluate("window.addEventListener('print-request', () => window.printRequested = true)")
    page.get_by_role("button", name="Print", exact=True).click()
    assert page.evaluate("window.printRequested")
    page.emulate_media(media="print")
    for selector in (".case-head", "#request", "#conversation", "#activity", ".action-column", ".topbar"):
        expect(page.locator(selector)).to_be_hidden()
    expect(page.locator("#quotation")).to_contain_text("Supply the first bearing now.")
    expect(page.locator("#quotation")).to_contain_text("Delivery date unconfirmed")
    expect(page.locator("#quotation")).to_contain_text("Sample quotation")
    assert page.pdf(format="A4").startswith(b"%PDF")
    page.emulate_media(media="screen")


def commercial_hold_and_navigation(page: Page, address: str) -> None:
    page.goto(address + "/enquiries/ENQ-1038")
    expect(page.get_by_role("heading", name="Stock or pricing needs attention")).to_be_visible()
    page.get_by_role("link", name="Review issues").click()
    expect(page.locator(":target")).to_have_id("evidence")
    expect(page.locator("#evidence .issues")).to_contain_text("stock")
    page.get_by_text("Recheck stock, price and specifications", exact=True).click()
    page.get_by_role("button", name="Check latest product details", exact=True).click()
    expect(page.get_by_role("heading", name="Stock or pricing needs attention")).to_be_visible()
    expect(page.get_by_role("button", name="Create quote")).to_have_count(0)
    page.get_by_role("link", name="Enquiry inbox", exact=True).click()
    page.get_by_role("link", name="Waiting for customer", exact=False).click()
    expect(page.get_by_role("heading", name="No matching enquiries")).to_be_visible()
    page.get_by_role("link", name="View all enquiries").click()
    page.get_by_role("link", name="Completed", exact=False).click()
    expect(page.locator(".inbox-table")).to_contain_text("Bearings and fasteners")
    expect(page.locator(".inbox-table")).not_to_contain_text("Availability of NPT adapters")


def long_subject_layout(page: Page, address: str) -> None:
    page.goto(address + "/enquiries/new")
    page.get_by_label("Customer account").select_option("Kauri Engineering")
    page.get_by_label("Enquiry subject").fill("B" * 180)
    page.get_by_label("Original request").fill("Please quote 1 x BRG-6205-2RS.")
    page.get_by_role("button", name="Save enquiry").click()
    detail = page.url
    for width in (320, 390, 760, 1024, 1366):
        page.set_viewport_size({"width": width, "height": 844})
        page.goto(detail)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.goto(address)
        assert page.evaluate("""() => {
            const table = document.querySelector('.inbox-table');
            const subject = document.querySelector('.subject');
            return table.clientWidth <= document.querySelector('.queue').clientWidth &&
                subject.scrollWidth <= subject.clientWidth;
        }""")


def exercise_review(page: Page, address: str) -> None:
    page.set_viewport_size({"width": 1366, "height": 900})
    clarification_and_reconciliation(page, address)
    multi_line_quote_and_print(page, address)
    commercial_hold_and_navigation(page, address)
    long_subject_layout(page, address)
