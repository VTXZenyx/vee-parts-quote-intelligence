"""Transactional workflow for the single synthetic employee workspace."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from vee.catalogue import FAMILIES, analyse, build_quote, current_record, partial_offer
from vee.catalogue_import import IMPORT_SCHEMA, active_parts, published_revision
from vee.database import transaction as _transaction

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
    ("ENQ-1037", "Coastal Fluid Systems", "Unidentified hydraulic fitting",
     "Please identify one hydraulic fitting from the attached photograph. We have no thread measurements.",
     [{"name": "inspection-fitting.webp", "text": "Synthetic inspection photograph. Thread standard, size and pressure rating are unconfirmed."}], ""),
)

ALLOWED = {
    "needs_clarification": {"save_clarification", "approve_clarification", "reject_clarification",
                            "reconcile_requirements", "refresh_evidence"},
    "awaiting_reply": {"simulate_reply"},
    "needs_verification": {"verify_match", "reject_match", "refresh_evidence"},
    "verified": {"create_quote", "refresh_evidence"},
    "draft_quote": {"edit_quote", "approve_quote", "reject_quote", "refresh_evidence"},
    "rejected": {"edit_quote", "refresh_evidence"},
    "approved": set(),
    "commercial_hold": {"refresh_evidence", "verify_partial"},
}

V2_SCHEMA = """
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


V3_SCHEMA = V2_SCHEMA + """
CREATE TABLE IF NOT EXISTS provider_mail (
    id INTEGER PRIMARY KEY,
    provider TEXT NOT NULL,
    mid TEXT NOT NULL,
    thread TEXT NOT NULL,
    internet TEXT NOT NULL,
    raw TEXT NOT NULL,
    normalised TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('held','accepted')),
    reason TEXT NOT NULL,
    enquiry_id TEXT REFERENCES enquiries(id),
    UNIQUE(provider, mid),
    CHECK ((status='accepted') = (enquiry_id IS NOT NULL))
);
"""


SCHEMA_VERSION = 4
SCHEMA = V3_SCHEMA + IMPORT_SCHEMA


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _audit(db, item, actor, action, message, at):
    db.execute("INSERT INTO events VALUES (?,?,?,?,?,?)",
               (item["id"], item["revision"], at, actor, action, message))


REVISED_HEADER = "Revised request:"
SERVICE_HAZARD = re.compile(
    r"\b(?:personnel|lifting|brak(?:e|es|ing)|safety|medical|oxygen|explosive|explosion|"
    r"flammable|hazardous|atex|food[- ](?:grade|contact)|human[- ]rated|load[- ]bearing)\b",
    re.IGNORECASE,
)


def _require_review(analysis, issue, question):
    for line in analysis["lines"]:
        line["issues"].append(issue)
        line["status"] = "review"
        line["sku"] = None
    analysis["questions"].append(question)
    analysis["ready"] = False


# Headings may repeat a request, name its family, or contain additional constraints.
# Only neutral administrative words may disappear during the comparison.
HEADING_WORDS = re.compile(
    r"\b(?:re|fw|fwd|rfq|request|for|quotation|quote|enquir(?:y|ies)|needed|"
    r"parts?|order|replacement|urgent|replenishment)\b", re.IGNORECASE
)


def _unresolved_subject(item, analysis):
    subject = item["subject"]
    if SERVICE_HAZARD.search(subject):
        return True
    # The fixed demo captions accompany curated evidence. Incoming subjects are customer text.
    if not item.get("message_id") and any(item["id"] == seed[0] and subject == seed[2] for seed in SEEDS):
        return False
    remainder = HEADING_WORDS.sub(" ", subject)
    lines = analysis["lines"]
    families = {line["family"] for line in lines}
    mentioned = set()
    for family, pattern in FAMILIES.items():
        family_pattern = r"\b(?:" + pattern + r")\b"
        if re.search(family_pattern, remainder, re.IGNORECASE):
            if family not in families:
                return True
            mentioned.add(family)
            remainder = re.sub(family_pattern, " ", remainder, flags=re.IGNORECASE)
    remainder = " ".join(remainder.strip(" ,:").rstrip(".").casefold().split())
    if not remainder:
        return False
    targets = [line for line in lines if not mentioned or line["family"] in mentioned]
    quantity = re.fullmatch(r"(?:(?:qty|quantity)\s*[:=]?\s*)?(\d{1,4})", remainder)
    if quantity:
        return len(targets) != 1 or targets[0]["quantity"] != int(quantity[1])
    # Match the constraint on a single relevant line, never across products or
    # inside another reference. Ambiguous multi-line allocation needs clarification.
    # A digit inside a decimal or fraction cannot start or end a separate measurement.
    start = r"(?<![\w.,/+−-])" if remainder[0].isdigit() else r"(?<![\w-])"
    end = r"(?![\w-]|[.,/]\d)" if remainder[-1].isdigit() else r"(?![\w-])"
    pattern = start + re.escape(remainder) + end
    matches = [line for line in targets if re.search(pattern, " ".join(line["text"].casefold().split()))]
    return len(matches) != 1 or len(mentioned) > 1


def _omitted_attributes(previous, active, account, parts):
    required: dict[str, set[str]] = {}
    for message in previous:
        for line in analyse(message.removeprefix(REVISED_HEADER), account, parts=parts)["lines"]:
            fields = required.setdefault(line["family"], set())
            fields.update(line["attributes"])
            # Keep named requirements even when their unit or value could not be
            # compared. A later exact SKU alone cannot resolve an imperial bore,
            # pressure in psi, or a material absent from the catalogue.
            text = line["text"].casefold()
            fields.update(re.findall(r"\b(?:bore|stroke|width|length|pitch|outside diameter)\b", text))
            if re.search(r"\bod\b", text):
                fields.add("outside diameter")
            if re.search(r"\bpressure\b|\d\s*(?:psi[ag]?|[kmg]?pa|m?bar)\b", text):
                fields.add("pressure")
            if re.search(r"\b(?:grade|property class)\b", text):
                fields.add("grade")
            if re.search(r"\b(?:material|steel|brass|bronze|alumini?um|nylon|ceramic)\b", text):
                fields.add("material")
    # An unallocated measurement in a separate reply still needs resolution.
    unallocated = required.get("Unidentified", set())
    return sorted({field for line in active["lines"]
                   for field in (required.get(line["family"], set()) | unallocated)
                   if field not in line["attributes"]})


def _investigate(db, item):
    item["catalogue_revision"] = published_revision(db)
    parts = active_parts(db, item["catalogue_revision"])
    # Only inbound customer messages establish requirements.
    messages = [entry["body"] for entry in item["thread"] if entry["direction"] == "inbound"]
    basis = item.get("basis_inbound", 0)
    active = messages[basis:]
    if basis:
        active[0] = active[0][len(REVISED_HEADER):].strip()
    item["revised_request"] = ""
    content = "\n".join(active)
    analysis = analyse(content, account=item["customer"], parts=parts)
    if len(active) > 1 and active[-1].casefold().startswith(REVISED_HEADER.casefold()):
        item["revised_request"] = active[-1][len(REVISED_HEADER):].strip()
        _require_review(analysis, "Customer proposed a complete revised request.",
                        "Please confirm the revised list before replacing the previous request.")
    elif len(active) > 1:
        original = analyse(active[0], account=item["customer"], parts=parts)
        if len(original["lines"]) != len(analysis["lines"]):
            _require_review(analysis, "The reply introduces a separate item or quantity requiring reconciliation.",
                            "Please reply with 'Revised request:' followed by the complete list of products and quantities.")
    # An explicitly superseded part reference may change. Known service hazards still
    # require a qualified reviewer, even when omitted from the replacement message.
    if any(SERVICE_HAZARD.search(message) for message in messages[:basis]):
        _require_review(analysis, "The earlier enquiry contains conditions requiring a qualified technical reviewer.",
                        "Please refer the full enquiry history to a qualified technical reviewer.")
    if _unresolved_subject(item, analysis):
        _require_review(analysis, "The subject contains requirements not resolved in the active request.",
                        "Please confirm the subject requirements in the complete request and refer special service conditions to a technical reviewer.")
    for entry in item["thread"]:
        if not entry.get("provider"):
            continue
        if entry.get("attachments"):
            _require_review(analysis, "Only attachment metadata is available.",
                            "Please confirm all attachment requirements in the message text.")
        if entry["subject"] != item["subject"] and _unresolved_subject({**item, "subject": entry["subject"]}, analysis):
            _require_review(analysis, "A changed email subject contains unresolved requirements.",
                            "Please confirm the requirements from the changed subject.")
    if basis:
        omitted = _omitted_attributes(messages[:basis], analysis, item["customer"], parts)
        if omitted:
            fields = ", ".join(omitted)
            _require_review(analysis, f"Earlier specifications need explicit confirmation: {fields}.",
                            f"Please include the confirmed {fields} in the revised request.")
    if item.get("correction_hold"):
        _require_review(analysis, "An employee has flagged a requirement for correction.",
                        "Please supply a complete 'Revised request:' confirming all products, quantities and specifications.")
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
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise ValueError("This workspace requires a newer version of VEE.")
        for statement in SCHEMA.split(";"):
            if statement.strip():
                db.execute(statement)
        for index, (key, customer, subject, body, attachments, reply) in enumerate(SEEDS):
            if db.execute("SELECT 1 FROM enquiries WHERE id=?", (key,)).fetchone():
                continue
            received = f"2026-11-17T{15-index:02d}:10:00+00:00"
            _insert_enquiry(db, key, customer, subject, body, attachments, reply, received)

        if version < SCHEMA_VERSION:
            _recheck_legacy_decisions(db)
            db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")


def _recheck_legacy_decisions(db):
    """Retain historical snapshots and explicitly reopen unsafe decisions from earlier versions."""
    for row in db.execute("SELECT state FROM enquiries").fetchall():
        item = json.loads(row["state"])
        previous = item["extraction"]
        old_offer = partial_offer(previous)
        if not previous["ready"] and not old_offer:
            continue
        _investigate(db, item)
        old_items = [(line["sku"], line["quantity"]) for line in previous["lines"]]
        current_items = [(line["sku"], line["quantity"]) for line in item["extraction"]["lines"]]
        if (old_items == current_items and previous["ready"] == item["extraction"]["ready"]
                and old_offer == partial_offer(item["extraction"])):
            continue
        item.update(selected_skus=[], selected_sku=None)
        item["revision"] += 1
        db.execute("UPDATE enquiries SET revision=?,state=? WHERE id=?",
                   (item["revision"], json.dumps(item), item["id"]))
        _audit(db, item, "Workspace update", "recheck_requirements",
               "Reopened under updated verification rules. Earlier decisions and quotation versions are historical.", _now())


CUSTOMERS = tuple(sorted({seed[1] for seed in SEEDS} | {"Contract Only Engineering"}))


def _insert_enquiry(db, key, customer, subject, body, attachments, reply, received, message_id=None, envelope=None):
    item = {
        "id": key, "message_id": message_id, "customer": customer, "subject": subject, "body": body, "received_at": received,
        "sender": "maintenance@" + customer.lower().replace(" ", "-") + ".example",
        "attachments": attachments, "sample_reply": reply, "selected_sku": None,
        "selected_skus": [], "revision": 1, "thread": [
            {"author": customer, "body": body, "at": received, "direction": "inbound"}],
    }
    if envelope:
        item["sender"] = envelope["sender"]
        item["thread"][0].update(envelope)
    _investigate(db, item)
    db.execute("INSERT INTO enquiries VALUES (?,?,?)", (key, 1, json.dumps(item)))
    receipt = "Synthetic customer enquiry recorded."
    if envelope and envelope.get("provider"):
        receipt = f"Received {envelope['provider']} message {envelope['mid']} in the simulated inbox."
    _audit(db, item, "Mock mailbox", "received", receipt, received)


DEMO_RECIPIENT = "quotes@vee.example"
DEMO_ADDRESS = re.compile(r"[a-z0-9_+-]+(?:\.[a-z0-9_+-]+)*@(?:[a-z0-9]+(?:-[a-z0-9]+)*\.)+example")


def _message_id(value: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, AttributeError, TypeError) as error:
        raise ValueError("Use a valid synthetic message identifier.") from error


def _demo_address(value: str) -> str:
    address = value.strip().lower()
    if len(address) > 254 or not DEMO_ADDRESS.fullmatch(address):
        raise ValueError("Use a fictional email address ending in .example.")
    return address


def _delivery(db, message_id: str):
    row = db.execute("""
        SELECT enquiries.state FROM enquiries
        WHERE json_extract(state, '$.message_id') = ?
        OR EXISTS (
            SELECT 1 FROM json_each(enquiries.state, '$.thread') AS message
            WHERE json_extract(message.value, '$.message_id') = ?
        )
    """, (message_id, message_id)).fetchone()
    if row is None:
        return None
    saved = json.loads(row["state"])
    message = next((m for m in saved["thread"] if m.get("message_id") == message_id), None)
    return saved, message


def accepts_revision(item: dict) -> bool:
    return item["status"] == "approved" and bool(item["thread"][0].get("message_id"))


def _receive(path, message_id, customer, subject, body, *, envelope=None, enquiry_id=None, revision=None):
    message_id = _message_id(message_id)
    if customer not in CUSTOMERS:
        raise ValueError("Choose a synthetic account.")
    subject = _text(subject, "a subject")
    if len(subject) > (204 if enquiry_id else 200):
        raise ValueError("Limit the original subject to 200 characters.")
    body = _text(body, "the original request")
    if envelope:
        envelope = {**envelope, "subject": subject, "message_id": message_id, "reply_to": enquiry_id}
    with _transaction(path, write=True) as db:
        prior = _delivery(db, message_id)
        if prior:
            saved, message = prior
            if envelope:
                matches = (message and message["direction"] == "inbound"
                           and (customer, body) == (saved["customer"], message["body"])
                           and all(message.get(key) == value for key, value in envelope.items()))
            else:
                matches = not message and (saved["customer"], saved["subject"], saved["body"]) == (customer, subject, body)
            if not matches:
                raise ValueError("This message ID was already received with different content or conversation.")
            return saved["id"], True

        if enquiry_id:
            item = _load(db, enquiry_id)
            expected = reply_envelope(item)
            if any(envelope[key] != expected[key] for key in ("sender", "recipient")) or customer != expected["customer"]:
                raise ValueError("Reply addresses and account must match the selected conversation.")
            if subject != expected["subject"]:
                raise ValueError("The reply subject must match the selected conversation.")
            if accepts_revision(item):
                if str(revision) != str(item["revision"]):
                    raise ValueError("This enquiry has changed. Review the latest revision and retry.")
                if not body.casefold().startswith(REVISED_HEADER.casefold()) or not body[len(REVISED_HEADER):].strip():
                    raise ValueError("Start with 'Revised request:' and supply the complete replacement order.")
                at = _now()
                _record_message(item, "inbound", body, at)
                item["thread"][-1].update(envelope)
                item.update(selected_skus=[], selected_sku=None, sample_reply="")
                _investigate(db, item)
                _save_revision(db, item, "Mock mailbox", "recheck_requirements",
                               "Received a complete revised order. Earlier approval is historical.", at)
                return item["id"], False
            _apply(db, item, "simulate_reply", {"revision": revision, "body": body}, envelope)
            return item["id"], False

        key = _next_key(db)
        _insert_enquiry(db, key, customer, subject, body, [], "", _now(), message_id, envelope)
        return key, False


def _next_key(db):
    sequence = db.execute("SELECT coalesce(max(cast(substr(id,5) AS integer)),1042)+1 FROM enquiries").fetchone()[0]
    return f"ENQ-{sequence}"


def receive(path: str | Path, message_id: str, customer: str, subject: str, body: str) -> str:
    """Record the original local intake form, atomically deduplicating retries."""
    return _receive(path, message_id, customer, subject, body)[0]


def receive_demo_email(
    path: str | Path, message_id: str, customer: str, sender: str, recipient: str, subject: str, body: str,
    *, enquiry_id: str | None = None, revision: str | None = None,
) -> tuple[str, bool]:
    """Persist one fictional email and its workflow effect in the same transaction."""
    envelope = {"sender": _demo_address(sender), "recipient": _demo_address(recipient)}
    return _receive(path, message_id, customer, subject, body, envelope=envelope, enquiry_id=enquiry_id, revision=revision)


def reply_envelope(item: dict) -> dict[str, str]:
    original = item["thread"][0]
    return {"customer": item["customer"], "sender": item["sender"],
            "recipient": original.get("recipient", DEMO_RECIPIENT), "subject": f"Re: {item['subject']}"}


def replay_demo_email(path: str | Path, message_id: str) -> tuple[str, bool]:
    with _transaction(path) as db:
        prior = _delivery(db, _message_id(message_id))
    if not prior:
        raise KeyError(message_id)
    item, message = prior
    if not message or message["direction"] != "inbound":
        raise KeyError(message_id)
    return receive_demo_email(path, message_id, item["customer"], message["sender"], message["recipient"],
                              message["subject"], message["body"], enquiry_id=message["reply_to"])


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


def queue_summaries(path: str | Path) -> list[dict]:
    """Read the inbox fields without loading quote versions, evidence or events."""
    with _transaction(path) as db:
        rows = db.execute("""
            SELECT id, json_extract(state, '$.customer') AS customer,
                   json_extract(state, '$.subject') AS subject,
                   json_extract(state, '$.status') AS status,
                   json_extract(state, '$.received_at') AS received_at,
                   json_extract(state, '$.extraction.urgent') AS urgent
              FROM enquiries ORDER BY id DESC
        """)
        return [{**dict(row), "extraction": {"urgent": bool(row["urgent"])}} for row in rows]


def inbox(path: str | Path) -> list[dict]:
    with _transaction(path) as db:
        return [_result(db, json.loads(row["state"])) for row in
                db.execute("SELECT state FROM enquiries ORDER BY id DESC")]


def _newly_resolved(db, item):
    if (item["status"] != "needs_clarification" or item["extraction"]["ready"]
            or item.get("correction_hold") or item.get("revised_request")):
        return False
    # Old, unopened backups can still be inspected through the read-only API.
    if db.execute("PRAGMA user_version").fetchone()[0] < SCHEMA_VERSION:
        return False
    if item.get("catalogue_revision", 0) >= published_revision(db):
        return False
    refreshed = item.copy()
    _investigate(db, refreshed)
    return refreshed["status"] in {"needs_verification", "commercial_hold"}


def detail(path: str | Path, id: str) -> dict:
    with _transaction(path) as db:
        item = _load(db, id)
        if _newly_resolved(db, item):
            item["catalogue_refresh_available"] = True
        return _result(db, item)


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


def _verified_skus(item, parts, *, partial=False):
    analysis = item["extraction"]
    skus = [line["sku"] for line in analysis["lines"]]
    if ((not analysis["ready"] and not (partial and partial_offer(analysis))) or not skus or any(not sku for sku in skus)
            or any(line["status"] != "verified" for line in analysis["lines"])):
        raise ValueError("Resolve the outstanding technical questions before verification.")
    evidence = _technical_evidence(item)
    if len(evidence) != len(skus):
        raise ValueError("Refresh the catalogue evidence for every selected product.")
    for line, saved in zip(analysis["lines"], evidence):
        # New shelf lines can make a previously unique specification match ambiguous.
        if not line.get("reference"):
            fresh = analyse(line["text"], item["customer"], parts=parts)["lines"][0]
            if fresh["sku"] != line["sku"]:
                raise ValueError("Refresh the evidence. The catalogue match has changed.")
        current = current_record(saved["sku"], item["customer"], parts=parts)
        if not current or any(current.get(k) != saved.get(k)
                              for k in ("sku", "name", "family", "specs", "source", "discontinued")):
            raise ValueError("Catalogue specifications changed. Refresh the evidence and verify each product again.")
        if any(current.get(k) != saved.get(k) for k in ("stock", "unit_price", "price_basis", "commercial_source")):
            raise ValueError("Refresh the changed stock or price and verify the product again.")
    return skus


def _commercial(db, item, quantities=None):
    parts = active_parts(db)
    partial = not item["extraction"]["ready"]
    if _verified_skus(item, parts, partial=partial) != item["selected_skus"]:
        raise ValueError("Verify each selected product before preparing a quotation.")
    return build_quote(item["extraction"], account=item["customer"], quantities=quantities, partial=partial, parts=parts)


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
    quote = _commercial(db, item, quantities)
    first = quote["lines"][0]
    quote.update(version=version, notes=notes, created_at=at, catalogue_revision=published_revision(db),
                 technical_evidence=_technical_evidence(item), sku=first["sku"],
                 unit_price=first["unit_price"], quantity=first["quantity"])
    db.execute("INSERT INTO quotes VALUES (?,?,?)", (item["id"], version, json.dumps(quote)))
    item["status"] = "draft_quote"
    return f"Saved quotation version {version} for {quote['currency']} {quote['total']} including GST."


def _transition(db, item, action, fields, at, envelope=None):
    if action not in ALLOWED[item["status"]]:
        raise ValueError("This action is unavailable at the current enquiry stage.")
    if any("price" in key or key in {"discount", "subtotal", "gst", "total"} for key in fields):
        raise ValueError("Prices and GST come from the authorised synthetic commercial records.")
    if action == "approve_quote" and fields.keys() - {"csrf", "action", "revision"}:
        raise ValueError("Save quotation edits as a new version before approving it.")
    if action == "refresh_evidence":
        if item["status"] == "needs_clarification" and not _newly_resolved(db, item):
            raise ValueError("This request still needs clarification before verification.")
        item.update(selected_skus=[], selected_sku=None)
        _investigate(db, item)
        return "Refreshed technical and commercial evidence. A new employee verification is required."
    if action == "reconcile_requirements":
        reason = _text(fields.get("reason"), "the reason for accepting the complete revised request")
        if not item.get("revised_request"):
            raise ValueError("A customer reply must explicitly provide the full revised request.")
        inbound = sum(entry["direction"] == "inbound" for entry in item["thread"])
        if any(inbound <= hold["after"] for hold in item.get("correction_hold", [])):
            raise ValueError("Obtain a new complete customer revision after the employee correction.")
        item.pop("correction_hold", None)
        item["basis_inbound"] = inbound - 1
        _investigate(db, item)
        return f"Accepted revised requirements from customer message {item['basis_inbound'] + 1}. {reason}"
    if action == "save_clarification":
        item["clarification"] = _text(fields.get("body"), "a clarification question")
        return "Saved clarification draft: " + item["clarification"]
    if action == "approve_clarification":
        item["clarification"] = _text(fields.get("body", item["clarification"]), "a clarification question")
        _record_message(item, "outbound", item["clarification"], at)
        address = reply_envelope(item)
        item["thread"][-1].update(
            sender=address["recipient"], recipient=address["sender"], subject=address["subject"],
            message_id=str(uuid4()), reply_to=item["id"],
        )
        item["status"] = "awaiting_reply"
        return "Employee approved the clarification and recorded it in the mock mailbox."
    if action == "reject_clarification":
        reason = _text(fields.get("reason"), "a rejection reason")
        item["clarification"] = ""
        return reason
    if action == "simulate_reply":
        body = _text(fields.get("body") or item["sample_reply"], "a synthetic customer reply")
        _record_message(item, "inbound", body, at)
        if envelope:
            item["thread"][-1].update(envelope)
        item["sample_reply"] = ""
        _investigate(db, item)
        return "Recorded a synthetic customer reply and rechecked the requirements."
    if action == "reject_match":
        reason = _text(fields.get("reason"), "a reason for rejecting this match")
        item["status"] = "needs_clarification"
        item["clarification"] = ""
        return reason
    if action in {"verify_match", "verify_partial"}:
        partial = action == "verify_partial"
        if partial and not partial_offer(item["extraction"]):
            raise ValueError("This request is ineligible for a partial quotation.")
        skus = _verified_skus(item, active_parts(db), partial=partial)
        submitted = [fields.get(f"sku_{i}", fields.get("sku") if len(skus) == 1 else None)
                     for i in range(len(skus))]
        if submitted != skus:
            raise ValueError("Confirm each resolved catalogue product against its evidence.")
        item.update(selected_skus=skus, selected_sku=skus[0], status="verified")
        records = [{key: evidence[key] for key in ("sku", "source", "specs")}
                   for evidence in _technical_evidence(item)]
        if partial:
            return "Employee verified the match and accepted a partial quotation: " + json.dumps(partial_offer(item["extraction"]))
        return "Employee verified catalogue evidence: " + json.dumps(records, ensure_ascii=False, sort_keys=True)
    if action in {"create_quote", "edit_quote"}:
        return _save_quote(db, item, action, fields, at)
    latest = _latest_quote(db, item)
    if action == "reject_quote":
        reason = _text(fields.get("reason"), "a rejection reason")
        item["status"] = "rejected"
        return f"Rejected quotation version {latest['version']}. {reason}"
    quantities = {line["sku"]: line["quantity"] for line in latest["lines"]}
    current = _commercial(db, item, quantities)
    if any(latest.get(key) != value for key, value in current.items()):
        raise ValueError("Commercial records changed. Save an updated quotation before approval.")
    item["status"] = "approved"
    return f"Employee approved quotation version {latest['version']} for {latest['currency']} {latest['total']}."


def _apply(db, item, action, fields, envelope=None):
    if str(fields.get("revision")) != str(item["revision"]):
        raise ValueError("This enquiry has changed. Review the latest revision and retry.")
    if action == "simulate_reply" and item["thread"][0].get("message_id") and not envelope:
        raise ValueError("Record this reply in the Demo Email Inbox.")
    at = _now()
    message = _transition(db, item, action, fields, at, envelope)
    actor = "Mock mailbox" if action == "simulate_reply" else "Demo employee"
    _save_revision(db, item, actor, action, message, at)
    return _result(db, item)


def _save_revision(db, item, actor, action, message, at):
    item["revision"] += 1
    db.execute("UPDATE enquiries SET revision=?,state=? WHERE id=?",
               (item["revision"], json.dumps(item), item["id"]))
    _audit(db, item, actor, action, message, at)


def act(path: str | Path, id: str, action: str, fields: dict) -> dict:
    """Apply exactly one explicitly requested transition to the displayed revision."""
    with _transaction(path, write=True) as db:
        return _apply(db, _load(db, id), action, fields)
