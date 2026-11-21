import io
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

from vee.web import WORKSPACE_COOKIE, create_app

INDEX = '/catalogue/import'
SAMPLE = Path(__file__).resolve().parents[1] / 'vee' / 'fixtures' / 'synthetic_catalogue.csv'


class CatalogueImportWebTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database = Path(directory.name) / 'original.sqlite3'
        self.app = create_app(self.database)
        self.client = self.app.test_client()

    def token(self):
        html = self.client.get(INDEX).get_data(as_text=True)
        return re.search(r'name="csrf" value="([^"]+)"', html)[1]

    def start(self):
        response = self.client.post('/demo-workspace/start', data={
            'csrf': self.token(), 'destination': 'catalogue',
        })
        self.assertEqual(response.location, INDEX)

    def stage(self, data=None, name='example.csv', synthetic='yes'):
        values = {'csrf': self.token(), 'source': 'sample'}
        if data is not None:
            values.update(source='file', synthetic=synthetic, file=(io.BytesIO(data), name))
        return self.client.post(INDEX, data=values)

    def test_original_and_other_demo_cannot_change_or_read_each_others_imports(self):
        from vee import catalogue_import

        self.assertEqual(self.stage().status_code, 409)
        self.start()
        first_cookie = self.client.get_cookie(WORKSPACE_COOKIE).value
        staged = self.stage()
        self.assertEqual(staged.status_code, 303)
        self.start()
        self.assertEqual(self.client.get(staged.location).status_code, 404)
        self.assertEqual(self.client.post(staged.location + '/activate', data={
            'csrf': self.token(), 'confirm': 'yes',
        }).status_code, 404)
        self.client.delete_cookie(WORKSPACE_COOKIE)
        self.assertEqual(self.client.get(staged.location).status_code, 404)
        self.assertEqual(catalogue_import.active_revision(self.database), 0)
        self.client.set_cookie(WORKSPACE_COOKIE, first_cookie)
        self.assertEqual(self.client.get(staged.location).status_code, 200)

    def test_file_limits_type_and_synthetic_confirmation_give_recoverable_errors(self):
        self.start()
        data = SAMPLE.read_bytes()
        for content, name, attestation, status in (
            (data, 'demo.txt', 'yes', 422), (data, 'demo.csv', '', 422),
            (b'bad,header\n1,2', 'demo.csv', 'yes', 422),
            (b'a' * 65537, 'demo.csv', 'yes', 413), (b'a' * 100000, 'demo.csv', 'yes', 413),
        ):
            with self.subTest(name=name, size=len(content), attestation=attestation):
                response = self.stage(content, name, attestation)
                self.assertEqual(response.status_code, status)
                self.assertIn(b'role="alert"', response.data)
                self.assertIn(b'Review sample CSV', response.data)
        self.assertEqual(self.client.post(INDEX, data={'source': 'sample'}).status_code, 403)
        self.assertEqual(self.stage(data).status_code, 303)
        # A maximum-size valid CSV must fit alongside its multipart form headers.
        padded = data.replace(b',Bearing,', b',' + b' ' * (65536 - len(data)) + b'Bearing,', 1)
        self.assertEqual(self.stage(padded).status_code, 303)

    def test_sample_download_diff_confirmation_restart_and_duplicate(self):
        self.start()
        sample = self.client.get(INDEX + '/sample.csv')
        with sample:
            self.assertEqual(sample.data, SAMPLE.read_bytes())
            self.assertIn('attachment', sample.headers['Content-Disposition'])
        staged = self.stage(SAMPLE.read_bytes())
        self.assertEqual(staged.status_code, 303)
        review = self.client.get(staged.location)
        for value in (b'BRG-6209-2RS', b'BRG-6206-ZZ', b'BRG-6202-ZZ',
                      b'NZD 15.75', b'NZD 16.20', b'Discontinued'):
            self.assertIn(value, review.data)
        self.assertEqual(self.stage().location, staged.location)
        activate = staged.location + '/activate'
        self.assertEqual(self.client.post(activate, data={'csrf': self.token()}).status_code, 422)
        self.assertIn(b'Activate catalogue revision', self.client.get(staged.location).data)
        response = self.client.post(activate, data={'csrf': self.token(), 'confirm': 'yes'}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Catalogue revision 1', response.data)
        self.assertNotIn(b'Activate catalogue revision', response.data)
        self.assertEqual(self.stage().status_code, 422)
        workspace = self.client.get_cookie(WORKSPACE_COOKIE).value
        reopened = create_app(self.database).test_client()
        reopened.set_cookie(WORKSPACE_COOKIE, workspace)
        self.assertIn(b'Catalogue revision 1', reopened.get(staged.location).data)

    def test_new_revision_blocks_activation_from_an_old_browser_tab(self):
        self.start()
        earlier = self.stage()
        later = self.stage(SAMPLE.read_bytes().replace(b',28.40', b',29.40'))
        self.assertEqual(earlier.status_code, 303)
        self.assertEqual(later.status_code, 303)
        form = {'csrf': self.token(), 'confirm': 'yes'}
        self.assertEqual(self.client.post(later.location + '/activate', data=form).status_code, 303)
        stale = self.client.post(earlier.location + '/activate', data=form)
        self.assertEqual(stale.status_code, 409)
        self.assertNotIn(b'Activate catalogue revision', stale.data)
        self.assertIn(b'Review a fresh file', stale.data)

    def test_failed_publication_and_unreadable_review_explain_recovery(self):
        from vee import catalogue_import

        self.start()
        stage = self.stage()
        cookie = self.client.get_cookie(WORKSPACE_COOKIE).value
        database = self.database.parent / (self.database.name + '.demos') / (cookie + '.sqlite3')
        activate = stage.location + '/activate'
        form = {'confirm': 'yes', 'csrf': self.token()}
        with sqlite3.connect(database) as db:
            db.execute("CREATE TRIGGER fail_publish BEFORE UPDATE ON catalogue_imports "
                       "BEGIN SELECT RAISE(ABORT, 'test_failure'); END")
        failed = self.client.post(activate, data=form)
        self.assertEqual(failed.status_code, 503)
        self.assertIn(b'Catalogue unavailable', failed.data)
        self.assertEqual(catalogue_import.active_revision(database), 0)
        with sqlite3.connect(database) as db:
            db.execute("DROP TRIGGER fail_publish")
            db.execute("UPDATE catalogue_imports SET payload=?", (b'damaged test fixture',))
        for result in (self.client.get(stage.location), self.client.post(activate, data=form)):
            self.assertEqual(result.status_code, 409)
            self.assertIn(b'role="alert"', result.data)
            self.assertNotIn(b'Activate catalogue revision', result.data)
        self.assertEqual(catalogue_import.active_revision(database), 0)
