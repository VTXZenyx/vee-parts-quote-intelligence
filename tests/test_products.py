import tempfile
import unittest
from pathlib import Path

from vee import catalogue_import
from vee.catalogue_web import SAMPLE
from vee.web import create_app


class WarehouseDirectory(unittest.TestCase):
    def test_search_displays_only_published_workspace_values(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "workspace.sqlite"
            client = create_app(path).test_client()
            url = "/catalogue/import/products?q=BRG-6209-2RS"
            self.assertIn(b"0 products", client.get(url).data)
            with client.session_transaction() as session:
                csrf = session["csrf"]
            client.post("/demo-workspace/start", data={"csrf": csrf})
            selected = client.get_cookie("vee_demo_workspace").value
            demo = path.parent / (path.name + ".demos") / (selected + ".sqlite3")
            stage = catalogue_import.stage(demo, SAMPLE.read_bytes())
            self.assertIn(b"0 products", client.get(url).data)
            catalogue_import.activate(demo, stage["id"], confirmed=True)
            self.assertIn(b"NZD 28.40", client.get(url).data)
            self.assertIn(b"0 products", client.get(url + "&family=Fastener").data)
            client.delete_cookie("vee_demo_workspace")
            self.assertIn(b"0 products", client.get(url).data)
