import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from vee import store


class FittingConversation(unittest.TestCase):
    def test_each_reply_narrows_question_and_replays_preserve_the_ledger(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "rounds.sqlite3"
            store.init(path)
            address = {"customer": "Coastal Fluid Systems", "sender": "buyer@coastal.example",
                           "recipient": store.DEMO_RECIPIENT}
            key, _ = store.receive_demo_email(path, str(uuid4()), **address, subject="Adapter quotation",
                                              body="2 hydraulic adapters")
            item = store.detail(path, key)
            first_question = item["clarification"]
            self.assertIn("thread", first_question)
            for body in ("BSPP, 1/4 in", "working pressure 200 bar, male to male"):
                form = {"revision": item["revision"], "body": item["clarification"]}
                awaiting = store.act(path, key, "approve_clarification", form)
                with self.assertRaises(ValueError):
                    store.act(path, key, "approve_clarification", form)
                uid = str(uuid4())
                store.receive_demo_email(path, uid, **address, subject="Re: Adapter quotation", body=body,
                                         enquiry_id=key, revision=str(awaiting["revision"]))
                item = store.detail(path, key)
                self.assertEqual(store.replay_demo_email(path, uid), (key, True))
                self.assertEqual(store.detail(path, key), item)
                if body.startswith("BSPP"):
                    self.assertNotIn("thread", item["clarification"])
                    self.assertIn("pressure", item["clarification"])
                    self.assertEqual(item["status"], "needs_clarification")
            self.assertEqual(item["status"], "needs_verification")
            self.assertEqual(item["extraction"]["lines"][0]["sku"], "ADP-BSPP-14")
            self.assertEqual([m["direction"] for m in item["thread"]],
                             ["inbound", "outbound", "inbound", "outbound", "inbound"])
            self.assertEqual(item["revision"], 5)
