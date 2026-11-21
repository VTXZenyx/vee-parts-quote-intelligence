"""Read-only, presenter-controlled perspective on synthetic customer quotations."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from flask import Blueprint, abort, g, render_template, request

from vee import store

# Each prepared case is reviewed in a separate examples database. References and
# accepted quantities are explicit so a fixture change fails the normal gates.
EXAMPLE_CASES = (
    ("Kauri Engineering", "Bearing quotation", "4 x BRG-6205-2RS", ("BRG-6205-2RS",), False),
    ("Kauri Engineering", "Bearing replenishment", "10 x BRG-6203-ZZ", ("BRG-6203-ZZ",), True),
    ("Harbour Packaging", "Cylinder quotation", "2 x CYL-32-100-DA", ("CYL-32-100-DA",), False),
    ("Southern Mill Services", "Parts quotation", "2 x BRG-6205-2RS\n3 x BLT-M12-80",
     ("BRG-6205-2RS", "BLT-M12-80"), False),
    ("Coastal Fluid Systems", "Hydraulic adapter quotation", "1 x ADP-BSPP-14", ("ADP-BSPP-14",), False),
    ("Otago Workshop", "Bearing quotation", "3 x BRG-6205-2RS", ("BRG-6205-2RS",), False),
    ("Contract Only Engineering", "Bearing quotation", "2 x BRG-6205-2RS", ("BRG-6205-2RS",), False),
)


def prepare_examples(destination: Path) -> None:
    """Publish a completed examples workspace once, even if two servers start."""
    if destination.is_file():
        return
    with TemporaryDirectory(dir=destination.parent) as directory:
        staged = Path(directory) / "samples.sqlite3"
        staged.touch(mode=0o600)
        store.init(staged)
        for account, subject, body, skus, partial in EXAMPLE_CASES:
            key = store.receive(staged, str(uuid4()), account, subject, body)
            item = store.detail(staged, key)
            fields = {f"sku_{index}": sku for index, sku in enumerate(skus)}
            verified = store.act(staged, key, "verify_partial" if partial else "verify_match",
                                 {"revision": item["revision"], **fields})
            draft = store.act(staged, key, "create_quote", {"revision": verified["revision"]})
            store.act(staged, key, "approve_quote", {"revision": draft["revision"]})
        # Hard-link only a closed database. Readers see the complete set or no file.
        try:
            os.link(staged, destination)
        except FileExistsError:
            pass


def current_approved(item: dict, version: str | None = None) -> bool:
    """Serve only the saved version bound to the current employee decision."""
    if item["status"] != "approved" or not item["quotes"]:
        return False
    quote = item["quotes"][-1]
    if version is not None and version != str(quote["version"]):
        return False
    # Advisory finding reviews can follow approval without changing the quote.
    decision = next((event for event in reversed(item["history"])
                     if event["action"] not in {"extract_findings", "review_finding"}), None)
    return bool(decision and decision["action"] == "approve_quote" and decision["detail"] ==
                f"Employee approved quotation version {quote['version']} for {quote['currency']} {quote['total']}.")


def _approved_for(path: Path, account: str) -> list[dict]:
    with store._transaction(path) as db:
        rows = db.execute("""
            SELECT state FROM enquiries
            WHERE json_extract(state, '$.customer') = ? AND json_extract(state, '$.status') = 'approved'
            ORDER BY id DESC
        """, (account,))
        items = [store._result(db, json.loads(row["state"])) for row in rows]
    return [item for item in items if current_approved(item)]


def make_blueprint(original: Path) -> Blueprint:
    samples = original.with_name(original.name + ".customer-examples-v1.sqlite3")
    prepare_examples(samples)
    blueprint = Blueprint("customer", __name__, url_prefix="/customer-preview")

    @blueprint.get("")
    def accounts() -> str:
        account = request.args.get("account", "Kauri Engineering")
        if account not in store.CUSTOMERS:
            abort(404)
        return render_template("customer_accounts.html", accounts=store.CUSTOMERS, account=account,
                               examples=_approved_for(samples, account), current=_approved_for(g.database, account),
                               workspace_source="workspace-" + (g.workspace or "original"))

    @blueprint.get("/<source>/<id>/<int:version>")
    def document(source: str, id: str, version: int) -> str | tuple[str, int]:
        account = request.args.get("account")
        if account not in store.CUSTOMERS:
            abort(404)
        if source == "examples":
            path = samples
        elif source == "workspace-" + (g.workspace or "original"):
            path = g.database
        else:
            abort(404)
        try:
            item = store.detail(path, id)
        except KeyError:
            abort(404)
        if item["customer"] != account:
            abort(404)
        if not current_approved(item, str(version)):
            title = "Approval required for this preview"
            saved = next((quote for quote in item["quotes"] if quote["version"] == version), None)
            if saved and version < item["quotes"][-1]["version"]:
                title = "Quotation superseded"
            elif saved and any(event["action"] == "approve_quote" and
                               event["detail"].startswith(f"Employee approved quotation version {version} ")
                               for event in item["history"]):
                title = "Approval withdrawn"
            return render_template("preview_unavailable.html", account=account, heading=title), 409
        return render_template("customer_preview.html", item=item, preview=True,
                               account=account, example=source == "examples")
    return blueprint
