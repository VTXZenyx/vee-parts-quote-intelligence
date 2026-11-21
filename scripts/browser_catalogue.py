"""Exercise isolated CSV upload, review, activation and a quote for an imported SKU."""

from pathlib import Path

from playwright.sync_api import Page, expect

from vee.catalogue_web import SAMPLE


def exercise_catalogue(page: Page, address: str, screenshots: Path | None = None) -> None:
    index = address + '/catalogue/import'
    page.goto(index)
    page.get_by_role('button', name='Open catalogue demo').press('Enter')
    expect(page.get_by_role('button', name='Review sample CSV')).to_be_visible()
    with page.expect_download() as downloaded:
        page.get_by_role('link', name='Download sample CSV').click()
    assert downloaded.value.suggested_filename == 'synthetic_catalogue.csv'
    assert downloaded.value.path().read_bytes() == SAMPLE.read_bytes()
    page.get_by_role('button', name='Review sample CSV').press('Enter')
    pending = page.url
    updated = page.locator('details.import-product').filter(has_text='BRG-6206-ZZ')
    updated.locator('summary').press('Enter')
    expect(updated.get_by_role('row', name='Net unit price NZD 15.75 NZD 16.20')).to_be_visible()
    for width in (1440, 1024, 768, 390, 320):
        page.set_viewport_size({'width': width, 'height': 900 if width > 390 else 844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
        assert updated.get_by_role('cell', name='NZD 16.20').bounding_box()['width'] > 45
        if screenshots:
            page.screenshot(path=screenshots / f'catalogue-comparison-{width}.png', full_page=True)

    tab = page.context.new_page()
    try:
        tab.goto(index)
        tab.get_by_text('Upload a synthetic CSV', exact=True).click()
        tab.get_by_label('Choose a CSV file').set_input_files({
            'name': 'bad.csv', 'mimeType': 'text/csv', 'buffer': b'sku,stock\nBRG-TEST,-1',
        })
        tab.get_by_label('This file contains only fictional').check()
        with tab.expect_response(lambda response: response.url == index and response.request.method == 'POST') as bad:
            tab.get_by_role('button', name='Review uploaded CSV').click()
        assert bad.value.status == 422
        expect(tab.get_by_role('alert')).to_be_visible()
        tab.get_by_label('Choose a CSV file').set_input_files({
            'name': 'synthetic-update.csv', 'mimeType': 'text/csv',
            'buffer': SAMPLE.read_bytes().replace(b',16.20', b',16.55'),
        })
        tab.get_by_label('This file contains only fictional').check()
        tab.get_by_role('button', name='Review uploaded CSV').press('Enter')
        tab.get_by_role('checkbox', name='I have reviewed').check()
        tab.get_by_role('button', name='Activate catalogue revision').click()
        expect(tab.get_by_role('heading', name='Catalogue revision 1')).to_be_visible()
    finally:
        tab.close()
    page.get_by_role('checkbox', name='I have reviewed').check()
    with page.expect_response(lambda response: response.url == pending + '/activate') as stale:
        page.get_by_role('button', name='Activate catalogue revision').click()
    assert stale.value.status == 409
    expect(page.get_by_role('link', name='Review a fresh file')).to_be_visible()
    expect(page.get_by_role('button', name='Activate catalogue revision')).to_have_count(0)
    page.goto(address + '/enquiries/new')
    page.get_by_label('Synthetic account').select_option('Kauri Engineering')
    page.get_by_label('Enquiry subject').fill('Bearing quotation')
    page.get_by_label('Original request').fill('2 x BRG-6209-2RS')
    page.get_by_role('button', name='Receive enquiry').click()
    page.get_by_role('checkbox', name='BRG-6209-2RS', exact=False).check()
    page.get_by_role('button', name='Verify match', exact=True).click()
    page.get_by_role('button', name='Create draft quotation').click()
    expect(page.locator('.totals')).to_contain_text('65.32')
    page.get_by_role('button', name='Return to original workspace').click()
    page.goto(index)
    expect(page.get_by_role('button', name='Open catalogue demo')).to_be_visible()
