"""Transactional workflow for the single synthetic employee workspace."""

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from vee.catalogue import analyse, build_quote, current_record

SEEDS: tuple[tuple[str, str, str, str, list[dict[str, str]], str], ...] = (
    ("ENQ-1042", "Harbour Packaging", "Replacement cylinders for packaging line",
     "We urgently need two replacement pneumatic cylinders for our packaging machine. The label has worn off.",
     [{"name": "cylinder-inspection.txt", "text": "Sample inspection note: the identification label is unreadable. "
        "The supplied note contains no measurements or verified part number."}],
     "Bore 32 mm, stroke 100 mm, double acting, ISO 15552, G1/8 ports, foot mount."),
    ("ENQ-1041", "Kauri Engineering", "Sealed bearing replenishment",
     "Please quote 4 x BRG-6205-2RS.", [], ""),
    ("ENQ-1040", "Southern Mill Services", "Bearings and fasteners for maintenance",
     "2 x BRG-6205-2RS\n3 x BLT-M12-80", [], ""),
    ("ENQ-1039", "Otago Workshop", "Cylinder with unreadable label",
     "Please identify one pneumatic cylinder. Our maintenance sheet does not list a part number.",
     [{"name": "maintenance-note.txt", "text": "Synthetic maintenance note: part number unreadable."}], ""),
    ("ENQ-1038", "Coastal Fluid Systems", "Availability of NPT adapters",
     "Please quote 2 x ADP-NPT-14.", [], ""),
)

ALLOWED = {
    "needs_clarification": {"save_clarification", "approve_clarification", "reject_clarification",
                            "reconcile_requirements"},
    "awaiting_reply": {"simulate_reply"},
    "needs_verification": {"verify_match", "reject_match", "refresh_evidence"},
    "verified": {"create_quote", "refresh_evidence"},
    "draft_quote": {"edit_quote", "approve_quote", "reject_quote", "refresh_evidence"},
    "rejected": {"edit_quote", "refresh_evidence"},
    "approved": set(),
    "commercial_hold": {"refresh_evidence"},
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS enquiries (
    id TEXT PRIMARY KEY,
    revision INTEGER NOT NULL,
    state TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    enquiry_id TEXT REFERENCES enquiries(id),
    revision INTEGER NOT NULL,
    at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL,
    PRIMARY KEY (enquiry_id, revision)
);
CREATE TABLE IF NOT EXISTS quotes (
    enquiry_id TEXT REFERENCES enquiries(id),
    version INTEGER NOT NULL,
    snapshot TEXT NOT NULL,
    PRIMARY KEY (enquiry_id, version)
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@contextmanager
def _transaction(path: str | Path, write: bool = False):
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _audit(db, item, actor, action, message, at):
    db.execute("INSERT INTO events VALUES (?,?,?,?,?,?)",
               (item["id"], item["revision"], at, actor, action, message))


REVISED_HEADER = "Revised request:"
SERVICE_HAZARD = re.compile(
    r"\b(?:personnel|lifting|brak(?:e|es|ing)|safety|medical|oxygen|explosive|explosion|"
    r"flammable|hazardous|atex|food[- ](?:grade|contact)|human[- ]rated|load[- ]bearing)\b",
    re.I,
)


def _require_review(analysis, issue, question):
    for line in analysis["lines"]:
        line["issues"].append(issue)
        line["status"] = "review"
        line["sku"] = None
    analysis["questions"].append(question)
    analysis["ready"] = False


def _investigate(item):
    # Only inbound customer messages establish requirements.
    messages = [entry["body"] for entry in item["thread"] if entry["direction"] == "inbound"]
    basis = item.get("basis_inbound", 0)
    active = messages[basis:]
    if basis:
        active[0] = active[0][len(REVISED_HEADER):].strip()
    item["revised_request"] = ""
    content = "\n".join(active)
    analysis = analyse(content, account=item["customer"])
    if len(active) > 1 and active[-1].casefold().startswith(REVISED_HEADER.casefold()):
        item["revised_request"] = active[-1][len(REVISED_HEADER):].strip()
        _require_review(analysis, "Customer proposed a complete revised request.",
                        "Please confirm the revised list before replacing the previous request.")
    elif len(active) > 1:
        original = analyse(active[0], account=item["customer"])
        if len(original["lines"]) != len(analysis["lines"]):
            _require_review(analysis, "The reply introduces a separate item or quantity requiring reconciliation.",
                            "Please reply with 'Revised request:' followed by the complete list of products and quantities.")
    # An explicitly superseded part reference may change. Known service hazards still
    # require a qualified reviewer, even when omitted from the replacement message.
    if any(SERVICE_HAZARD.search(message) for message in messages[:basis]):
        _require_review(analysis, "The earlier enquiry contains conditions requiring a qualified technical reviewer.",
                        "Please refer the full enquiry history to a qualified technical reviewer.")
    item["extraction"] = analysis
    item["candidates"] = [c for line in analysis["lines"] for c in line["candidates"]]
    if analysis["ready"]:
        item["status"] = "needs_verification"
    elif all(line["status"] == "verified" for line in analysis["lines"]):
        item["status"] = "commercial_hold"
    else:
        item["status"] = "needs_clarification"
    item["clarification"] = "\n".join(analysis["questions"])


def init(path: str | Path) -> None:
    with _transaction(path, write=True) as db:
        for statement in SCHEMA.split(";"):
            if statement.strip():
                db.execute(statement)
        for index, (key, customer, subject, body, attachments, reply) in enumerate(SEEDS):
            if db.execute("SELECT 1 FROM enquiries WHERE id=?", (key,)).fetchone():
                continue
            received = f"2026-11-17T{15-index:02d}:10:00+00:00"
            item = {
                "id": key, "customer": customer, "subject": subject, "body": body, "received_at": received,
                "sender": "maintenance@" + customer.lower().replace(" ", "-") + ".example",
                "attachments": attachments, "sample_reply": reply, "selected_sku": None,
                "selected_skus": [], "revision": 1, "thread": [
                    {"author": customer, "body": body, "at": received, "direction": "inbound"}],
            }
            _investigate(item)
            db.execute("INSERT INTO enquiries VALUES (?,?,?)", (key, 1, json.dumps(item)))
            _audit(db, item, "Mock mailbox", "received", "Synthetic customer enquiry recorded.", received)


def _load(db, key):
    row = db.execute("SELECT state FROM enquiries WHERE id=?", (key,)).fetchone()
    if row is None:
        raise KeyError(key)
    return json.loads(row["state"])


def _result(db, item):
    key = item["id"]
    item["history"] = [dict(row) for row in db.execute(
        "SELECT at,actor,action,detail,revision FROM events WHERE enquiry_id=? ORDER BY revision", (key,))]
    item["quotes"] = [json.loads(row["snapshot"]) for row in db.execute(
        "SELECT snapshot FROM quotes WHERE enquiry_id=? ORDER BY version", (key,))]
    return item


def inbox(path: str | Path) -> list[dict]:
    with _transaction(path) as db:
        return [_result(db, json.loads(row["state"])) for row in
                db.execute("SELECT state FROM enquiries ORDER BY id DESC")]


def detail(path: str | Path, id: str) -> dict:
    with _transaction(path) as db:
        return _result(db, _load(db, id))


def _text(value, label, *, required=True):
    if not isinstance(value, str) or len(value) > 8000 or (required and not value.strip()):
        raise ValueError(f"Enter {label} using up to 8,000 characters.")
    return value.strip()


def _record_message(item, direction, body, at):
    author = item["customer"] if direction == "inbound" else "Demo employee"
    item["thread"].append({"author": author, "at": at, "body": body, "direction": direction})


def _technical_evidence(item):
    return [candidate for line in item["extraction"]["lines"] for candidate in line["candidates"]
            if candidate["sku"] == line["sku"]]


def _verified_skus(item):
    analysis = item["extraction"]
    skus = [line["sku"] for line in analysis["lines"]]
    if (not analysis["ready"] or not skus or any(not sku for sku in skus)
            or any(line["status"] != "verified" for line in analysis["lines"])):
        raise ValueError("Resolve the outstanding technical questions before verification.")
    evidence = _technical_evidence(item)
    if len(evidence) != len(skus):
        raise ValueError("Refresh the catalogue evidence for every selected product.")
    for saved in evidence:
        current = current_record(saved["sku"], item["customer"])
        if not current or any(current.get(k) != saved.get(k)
                              for k in ("sku", "name", "family", "specs", "source", "discontinued")):
            raise ValueError("Catalogue specifications changed. Refresh the evidence and verify each product again.")
    return skus


def _commercial(item, quantities=None):
    if _verified_skus(item) != item["selected_skus"]:
        raise ValueError("Verify each selected product before preparing a quotation.")
    return build_quote(item["extraction"], account=item["customer"], quantities=quantities)


def _latest_quote(db, item):
    row = db.execute("SELECT snapshot FROM quotes WHERE enquiry_id=? ORDER BY version DESC LIMIT 1",
                     (item["id"],)).fetchone()
    if not row:
        raise ValueError("Prepare a draft before reviewing the quotation.")
    return json.loads(row["snapshot"])


def _edited_quantities(fields, previous):
    quantities = {line["sku"]: line["quantity"] for line in previous["lines"]}
    allowed = {"quantity_" + sku for sku in quantities}
    if len(quantities) == 1:
        allowed.add("quantity")
    if any(key.startswith("quantity") and key not in allowed for key in fields):
        raise ValueError("Identify each quoted product when editing its quantity.")
    for sku, old in quantities.items():
        raw = fields.get("quantity_" + sku, fields.get("quantity", old))
        if not str(raw).isascii() or not str(raw).isdecimal() or len(str(raw)) > 9:
            raise ValueError("Enter a positive whole quantity for each product.")
        quantities[sku] = int(raw)
    return quantities


def _save_quote(db, item, action, fields, at):
    notes = ""
    version = db.execute("SELECT COALESCE(MAX(version),0)+1 FROM quotes WHERE enquiry_id=?",
                         (item["id"],)).fetchone()[0]
    quantities = None
    if action == "edit_quote":
        previous = _latest_quote(db, item)
        quantities = _edited_quantities(fields, previous)
        notes = previous["notes"]
    notes = _text(fields.get("notes", notes), "quotation notes", required=False)
    quote = _commercial(item, quantities)
    first = quote["lines"][0]
    quote.update(version=version, notes=notes, created_at=at, technical_evidence=_technical_evidence(item), sku=first["sku"],
                 unit_price=first["unit_price"], quantity=first["quantity"])
    db.execute("INSERT INTO quotes VALUES (?,?,?)", (item["id"], version, json.dumps(quote)))
    item["status"] = "draft_quote"
    return f"Saved quotation version {version} for {quote['currency']} {quote['total']} including GST."


def _transition(db, item, action, fields, at):
    if action not in ALLOWED[item["status"]]:
        raise ValueError("This action is unavailable at the current enquiry stage.")
    if any("price" in key or key in {"discount", "subtotal", "gst", "total"} for key in fields):
        raise ValueError("Prices and GST come from the authorised synthetic commercial records.")
    if action == "approve_quote" and fields.keys() - {"csrf", "action", "revision"}:
        raise ValueError("Save quotation edits as a new version before approving it.")
    if action == "refresh_evidence":
        item.update(selected_skus=[], selected_sku=None)
        _investigate(item)
        return "Refreshed technical and commercial evidence. A new employee verification is required."
    if action == "reconcile_requirements":
        reason = _text(fields.get("reason"), "the reason for accepting the complete revised request")
        if not item.get("revised_request"):
            raise ValueError("A customer reply must explicitly provide the full revised request.")
        item["basis_inbound"] = sum(entry["direction"] == "inbound" for entry in item["thread"]) - 1
        _investigate(item)
        return f"Accepted revised requirements from customer message {item['basis_inbound'] + 1}. {reason}"
    if action == "save_clarification":
        item["clarification"] = _text(fields.get("body"), "a clarification question")
        return "Saved clarification draft: " + item["clarification"]
    if action == "approve_clarification":
        item["clarification"] = _text(fields.get("body", item["clarification"]), "a clarification question")
        _record_message(item, "outbound", item["clarification"], at)
        item["status"] = "awaiting_reply"
        return "Employee approved the clarification and recorded it in the mock mailbox."
    if action == "reject_clarification":
        reason = _text(fields.get("reason"), "a rejection reason")
        item["clarification"] = ""
        return reason
    if action == "simulate_reply":
        body = _text(fields.get("body") or item["sample_reply"], "a synthetic customer reply")
        _record_message(item, "inbound", body, at)
        item["sample_reply"] = ""
        _investigate(item)
        return "Recorded a synthetic customer reply and rechecked the requirements."
    if action == "reject_match":
        reason = _text(fields.get("reason"), "a reason for rejecting this match")
        item["status"] = "needs_clarification"
        item["clarification"] = ""
        return reason
    if action == "verify_match":
        skus = _verified_skus(item)
        submitted = [fields.get(f"sku_{i}", fields.get("sku") if len(skus) == 1 else None)
                     for i in range(len(skus))]
        if submitted != skus:
            raise ValueError("Confirm each resolved catalogue product against its evidence.")
        item.update(selected_skus=skus, selected_sku=skus[0], status="verified")
        return "Employee verified the catalogue evidence for " + ", ".join(skus) + "."
    if action in {"create_quote", "edit_quote"}:
        return _save_quote(db, item, action, fields, at)
    latest = _latest_quote(db, item)
    if action == "reject_quote":
        reason = _text(fields.get("reason"), "a rejection reason")
        item["status"] = "rejected"
        return f"Rejected quotation version {latest['version']}. {reason}"
    quantities = {line["sku"]: line["quantity"] for line in latest["lines"]}
    current = _commercial(item, quantities)
    if any(latest.get(key) != value for key, value in current.items()):
        raise ValueError("Commercial records changed. Save an updated quotation before approval.")
    item["status"] = "approved"
    return f"Employee approved quotation version {latest['version']} for {latest['currency']} {latest['total']}."


def act(path: str | Path, id: str, action: str, fields: dict) -> dict:
    """Apply exactly one explicitly requested transition to the displayed revision."""
    with _transaction(path, write=True) as db:
        item = _load(db, id)
        if str(fields.get("revision")) != str(item["revision"]):
            raise ValueError("This enquiry has changed. Review the latest revision and retry.")
        at = _now()
        message = _transition(db, item, action, fields, at)
        item["revision"] += 1
        db.execute("UPDATE enquiries SET revision=?,state=? WHERE id=?",
                   (item["revision"], json.dumps(item), id))
        actor = "Mock mailbox" if action == "simulate_reply" else "Demo employee"
        _audit(db, item, actor, action, message, at)
        return _result(db, item)
