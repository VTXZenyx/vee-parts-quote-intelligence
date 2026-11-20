"""Use provider identities across out-of-order, duplicate and same-subject browser deliveries."""

from playwright.sync_api import Page, expect


def exercise_providers(page: Page, address: str) -> None:
    page.goto(address + "/demo-email")
    page.get_by_role("link", name="Provider fixtures").click()

    def receive(key):
        page.get_by_label("Simulated provider message").select_option(key)
        page.get_by_role("button", name="Import message", exact=True).click()

    receive("gmail-details")
    reply = page.locator('details[data-provider="gmail"][data-provider-id="18c1"]')
    expect(reply.locator("summary").first).to_contain_text("Held")
    receive("graph-cylinder")
    receive("gmail-cylinder")
    reply.locator("summary").first.click()
    reply.get_by_role("button", name="Retry association").click()
    expect(reply.locator("summary").first).to_contain_text("Accepted")
    reply.locator("summary").first.click()
    link = reply.get_by_role("link", name="Open ENQ-")
    enquiry_url = link.get_attribute("href")
    link.click()
    expect(page.locator("#conversation li")).to_have_count(2)
    expect(page.locator("#findings")).to_contain_text("<c1@mail.example>")
    page.get_by_role("link", name="Read source message 2").click()
    expect(page.locator(":target")).to_have_id("customer-message-2")
    expect(page.locator(":target")).to_contain_text("Bore 32 mm")
    page.get_by_text("Change processing method", exact=True).click()
    page.get_by_label("Processing method").select_option("mock")
    page.get_by_role("button", name="Process selected message").click()
    expect(page.locator("#findings")).to_contain_text("Mock model")
    page.get_by_text("Review or correct a finding", exact=True).click()
    page.get_by_label("Evidence or reason").fill("Compared to the source dimensions")
    page.get_by_role("button", name="Record finding review").click()
    expect(page.locator("#findings")).to_contain_text("Employee reviewed")
    page.get_by_role("checkbox", name="Confirm CYL-32-100-DA").check()
    page.get_by_role("button", name="Verify match", exact=True).click()
    page.get_by_role("button", name="Create draft quotation").click()
    expect(page.locator("#quotation")).to_contain_text("316.25")
    page.get_by_role("button", name="Approve version 1").click()
    state = page.locator("#conversation, #activity, #quotation")
    before = state.all_text_contents()
    page.goto(address + "/demo-email")
    page.get_by_role("link", name="Provider fixtures").click()
    reply.locator("summary").first.click()
    reply.get_by_role("button", name="Replay provider delivery").click()
    expect(page.get_by_role("status")).to_contain_text("Duplicate")
    page.goto(address + enquiry_url)
    assert state.all_text_contents() == before
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
