"""Drive the offline demo email workflow through the employee interface."""

from unittest.mock import patch

from playwright.sync_api import Page, expect


def exercise_demo(page: Page, address: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(address)
    page.get_by_role("link", name="Email inbox").press("Enter")
    page.get_by_label("Example email").select_option("cylinder")
    page.get_by_role("button", name="Load example").click()
    expect(page.get_by_role("heading", name="Email inbox")).to_be_visible()
    expect(page.get_by_label("From")).to_have_value("maintenance@harbour.example")
    page.get_by_role("button", name="Start fresh demo").click()
    expect(page.locator(".environment")).to_have_text("Demo Mode")
    expect(page.locator(".workspace-switch")).to_contain_text("separate demo workspace")
    expect(page.get_by_role("status")).to_contain_text("Fresh demo")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

    message_id = page.get_by_label("Message ID", exact=True).input_value()
    # Keep the original and outbound clarification in the same second to reproduce the sort tie.
    with patch("vee.store._now", return_value="2026-11-20T12:00:00+00:00"):
        page.get_by_role("button", name="Add email to enquiries").click()
        expect(page.get_by_role("heading", name="Cylinder quotation", exact=True)).to_be_visible()
        expect(page.get_by_role("heading", name="Review the question")).to_be_visible()
        expect(page.locator("#request .issues")).to_contain_text("bore")
        page.get_by_role("button", name="Approve question").click()
        expect(page.get_by_role("link", name="Add customer reply")).to_be_visible()
    page.get_by_role("link", name="Add customer reply").click()
    expect(page.get_by_label("From")).to_have_value("maintenance@harbour.example")
    page.get_by_text("Try a reply example", exact=True).press("Enter")
    page.get_by_role("link", name="Supply the missing cylinder measurements").click()
    with patch("vee.store._now", return_value="2026-11-20T12:00:01+00:00"):
        page.get_by_role("button", name="Save customer reply").click()
        expect(page.get_by_role("heading", name="Check the product")).to_be_visible()
    expect(page.locator("#conversation li")).to_have_count(3)
    page.get_by_role("checkbox", name="Confirm CYL-32-100-DA").check()
    page.get_by_role("button", name="Confirm product", exact=True).click()
    page.get_by_role("button", name="Create quote").click()
    expect(page.locator("#quotation .requested-quantity")).to_have_text("Requested2")
    expect(page.locator("#quotation .quoted-quantity")).to_have_text("Quoted2")
    expect(page.locator("#quotation")).to_contain_text("316.25")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.get_by_role("link", name="Enquiry inbox", exact=True).click()
    page.get_by_role("link", name="Awaiting approval").click()
    page.get_by_role("link", name="Cylinder quotation").click()
    page.get_by_role("button", name="Approve version 1").click()
    expect(page.locator("#quotation")).to_contain_text("Approved")

    enquiry_url = page.url
    enquiry_id = page.locator(".case-id").inner_text()
    enquiry_records = page.locator("#conversation li, #activity li, #quotation")
    records_before = enquiry_records.all_text_contents()

    # A separate delivery with exactly the same subject must remain a distinct enquiry.
    page.goto(address + "/demo-email?scenario=cylinder")
    with patch("vee.store._now", return_value="2026-11-20T12:00:02+00:00"):
        page.get_by_role("button", name="Add email to enquiries").click()
        expect(page.get_by_role("heading", name="Cylinder quotation", exact=True)).to_be_visible()
    assert page.url != enquiry_url
    page.get_by_role("link", name="Enquiry inbox", exact=True).click()
    enquiry_rows = page.locator(".inbox-table tbody tr")
    expect(enquiry_rows.filter(has_text="Cylinder quotation")).to_have_count(2)
    rows_before = enquiry_rows.all_text_contents()

    page.get_by_role("link", name="Email inbox").click()
    page.get_by_role("link", name="Message history", exact=True).click()
    history = page.locator(".mail-history")
    messages = history.locator("li")
    expect(messages).to_have_count(4)
    expect(history.get_by_text("Cylinder quotation", exact=True)).to_have_count(2)
    messages_before = messages.all_text_contents()
    replay_form = page.locator(f'form[action="/demo-email/{message_id}/replay"]')
    original = messages.filter(has=replay_form)
    expect(original).to_have_count(1)
    expect(original.locator(":scope > details > summary")).to_contain_text(f"Received · {enquiry_id}")
    original.locator(":scope > details > summary").click()
    original.get_by_role("button", name="Replay delivery", exact=True).click()
    expect(page.get_by_role("status")).to_contain_text(f"Duplicate delivery recognised for {enquiry_id}.")
    assert messages.all_text_contents() == messages_before

    page.get_by_role("link", name="Enquiry inbox", exact=True).click()
    assert enquiry_rows.all_text_contents() == rows_before
    page.goto(enquiry_url)
    expect(page.locator("#quotation")).to_contain_text("Approved")
    assert enquiry_records.all_text_contents() == records_before
    page.get_by_role("link", name="Email inbox").click()

    picker = page.get_by_label("Example email")
    picker.select_option("stock")
    page.get_by_role("button", name="Load example").click()
    page.get_by_role("button", name="Add email to enquiries").click()
    expect(page.get_by_role("heading", name="Stock or pricing needs attention")).to_be_visible()
    expect(page.get_by_role("button", name="Create quote")).to_have_count(0)
    page.get_by_role("button", name="Return to original workspace").click()
    expect(page.locator(".environment")).to_have_text("Demo Mode")
    expect(page.locator(".workspace-switch")).to_have_count(0)
    expect(page.locator(".inbox-table")).not_to_contain_text("Cylinder quotation")
