"""Receive a bounded plain-text subset of Gmail and Graph messages in the demo mailbox."""

import base64
import json
import re
from datetime import UTC, datetime
from email.utils import parseaddr
from pathlib import Path

from vee import store

FIXTURES = json.loads(
    (Path(__file__).with_name("fixtures") / "provider_mail.json").read_text()
)
ACCOUNTS = {
    "maintenance@harbour.example": "Harbour Packaging",
    "buyer@kauri.example": "Kauri Engineering",
    "buyer@southern-mill.example": "Southern Mill Services",
    "buyer@coastal-fluid.example": "Coastal Fluid Systems",
}
RFC_ID = re.compile(r"<[^\s<>@]+@[^\s<>@]+>")


def field(value, name, limit=255):
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > limit
        or "\x00" in value
    ):
        raise ValueError(f"Invalid or missing {name}.")
    return value


def headers(values):
    result = {}
    for header in values:
        name = field(header["name"], "header name").lower()
        if name not in {
            "message-id",
            "references",
            "in-reply-to",
            "from",
            "to",
            "subject",
        }:
            continue
        if name in result:
            raise ValueError(f"Conflicting {name} headers.")
        result[name] = field(header["value"], "header value", 2048)
    return result


def gmail_content(part, bodies, files, depth=0):
    if depth > 6:
        raise ValueError("Unsupported MIME nesting.")
    mime = field(part["mimeType"], "MIME type")
    if part.get("filename"):
        files.append(
            {
                "name": field(part["filename"], "filename"),
                "type": mime,
                "size": part["body"]["size"],
            }
        )
    elif mime.startswith("multipart/"):
        for child in part["parts"]:
            gmail_content(child, bodies, files, depth + 1)
    elif mime == "text/plain":
        data = field(part["body"]["data"], "plain text body", 44000)
        decoded = base64.b64decode(
            data + "=" * (-len(data) % 4), altchars=b"-_", validate=True
        )
        if len(decoded) != part["body"]["size"]:
            raise ValueError("Gmail body size disagrees with its contents.")
        bodies.append(decoded.decode("utf-8"))
    elif mime != "text/html":
        raise ValueError("Unsupported MIME content. Review the original fixture.")


def normalise(provider: str, raw: dict) -> dict:
    try:
        if len(json.dumps(raw)) > 64000:
            raise ValueError("Message exceeds the fixture size limit.")
        files: list[dict] = []
        if provider == "gmail":
            h = headers(raw["payload"]["headers"])
            mid, thread, internet = raw["id"], raw["threadId"], h["message-id"]
            sender, recipient, subject = h["from"], h["to"], h["subject"]
            # Accept one address per header in this single-mailbox simulation.
            if any("," in v or ";" in v for v in (sender, recipient)):
                raise ValueError("Expected one sender and one recipient.")
            sender, recipient = parseaddr(sender)[1], parseaddr(recipient)[1]
            at = datetime.fromtimestamp(int(raw["internalDate"]) / 1000, UTC)
            bodies: list[str] = []
            gmail_content(raw["payload"], bodies, files)
            if len(bodies) != 1:
                raise ValueError("Expected one plain text message body.")
            body = bodies[0]
        elif provider == "outlook":
            h = headers(raw.get("internetMessageHeaders", []))
            mid, thread, internet = (
                raw["id"],
                raw["conversationId"],
                raw["internetMessageId"],
            )
            if h.get("message-id", internet) != internet:
                raise ValueError("Conflicting internet message identifiers.")
            sender = raw["from"]["emailAddress"]["address"]
            if (
                len(raw["toRecipients"]) != 1
                or raw["body"]["contentType"].lower() != "text"
            ):
                raise ValueError("Expected one recipient and a plain text Graph body.")
            recipient = raw["toRecipients"][0]["emailAddress"]["address"]
            subject, body = raw["subject"], raw["body"]["content"]
            at = datetime.fromisoformat(raw["receivedDateTime"])
            if at.tzinfo is None:
                raise ValueError("Received time needs a timezone.")
            for attachment in raw.get("attachments", []):
                files.append(
                    {
                        "name": field(attachment["name"], "filename"),
                        "type": field(attachment["contentType"], "attachment type"),
                        "size": attachment["size"],
                    }
                )
            if raw.get("hasAttachments", bool(files)) != bool(files):
                raise ValueError("Attachment metadata is incomplete.")
        else:
            raise ValueError("Unknown provider.")
        internet = field(internet, "internet message ID")
        refs = h.get("references", "").split()
        parent = h.get("in-reply-to", "")
        if (
            len(refs) > 20
            or len(set(refs)) != len(refs)
            or any(
                not RFC_ID.fullmatch(v)
                for v in [internet, *refs, *([parent] if parent else [])]
            )
            or internet in [parent, *refs]
            or (refs and parent and refs[-1] != parent)
        ):
            raise ValueError("Conflicting or malformed reply references.")
        if len(files) > 12 or any(
            type(f["size"]) is not int or not 0 <= f["size"] <= 25000000 for f in files
        ):
            raise ValueError("Invalid attachment metadata.")
        return {
            "provider": provider,
            "mid": field(mid, "provider message ID"),
            "thread": field(thread, "conversation ID"),
            "internet": internet,
            "parent": parent or (refs[-1] if refs else ""),
            "references": refs,
            "sender": store._demo_address(field(sender, "sender")),
            "recipient": store._demo_address(field(recipient, "recipient")),
            "subject": field(subject, "subject", 200),
            "body": field(body, "body", 8000),
            "at": at.astimezone(UTC).isoformat(),
            "attachments": files,
        }
    except (
        KeyError,
        IndexError,
        AttributeError,
        TypeError,
        OverflowError,
        OSError,
    ) as error:
        raise ValueError(
            "Malformed provider message. Check identifiers, timestamp, addresses and body."
        ) from error


def _associate(db, m):
    if m["recipient"] != store.DEMO_RECIPIENT or m["sender"] not in ACCOUNTS:
        return None, "The sender or recipient has no synthetic account mapping."
    if re.match(r"^\s*(?:(?:re|aw):\s*)*(?:fw|fwd):", m["subject"], re.IGNORECASE):
        return None, "Forwarded content needs a manual origin check."
    if db.execute(
        "SELECT 1 FROM provider_mail WHERE internet=? AND status='accepted'",
        (m["internet"],),
    ).fetchone():
        return None, "Another delivery already claims this internet message ID."
    thread = db.execute(
        """SELECT * FROM provider_mail WHERE provider=? AND thread=? AND status='accepted'
                           """,
        (m["provider"], m["thread"]),
    ).fetchall()
    if not m["parent"]:
        if thread or re.match(r"^\s*(re|aw):", m["subject"], re.IGNORECASE):
            return (
                None,
                "A reply or reused conversation ID lacks a verified parent message.",
            )
        return "", ""
    parents = {r["internet"]: r for r in thread}
    if m["parent"] not in parents or any(ref not in parents for ref in m["references"]):
        return (
            None,
            "A referenced message is missing from this provider conversation. Retry after it arrives.",
        )
    if re.search(
        r"\b(?:separate|unrelated|new) (?:enquiry|inquiry|request|order)\b",
        m["subject"] + "\n" + m["body"],
        re.IGNORECASE,
    ):
        return (
            None,
            "The message describes a separate request inside an existing conversation.",
        )
    parent = parents[m["parent"]]
    item = store._load(db, parent["enquiry_id"])
    # Workflow order can differ from receipt order when a held child is retried.
    last = next(
        entry for entry in reversed(item["thread"]) if entry["direction"] == "inbound"
    )
    if last.get("internet") != m["parent"] or m["at"] < last["at"]:
        return (
            None,
            "The reply branches from older evidence. An employee must reconcile the sequence.",
        )
    if last["sender"] != m["sender"]:
        return None, "The reply sender differs from the original customer."
    return item["id"], ""


def _accept(db, m, key):
    envelope = {
        k: m[k]
        for k in (
            "provider",
            "mid",
            "internet",
            "sender",
            "recipient",
            "subject",
            "attachments",
        )
    }
    if not key:
        key = store._next_key(db)
        attachments = [
            {
                "name": f["name"],
                "text": f"Metadata only · {f['type']} · {f['size']} bytes",
            }
            for f in m["attachments"]
        ]
        store._insert_enquiry(
            db,
            key,
            ACCOUNTS[m["sender"]],
            m["subject"],
            m["body"],
            attachments,
            "",
            m["at"],
            envelope=envelope,
        )
    else:
        item = store._load(db, key)
        store._record_message(item, "inbound", m["body"], m["at"])
        item["thread"][-1].update(envelope)
        item.update(selected_skus=[], selected_sku=None, sample_reply="")
        store._investigate(item)
        store._save_revision(
            db,
            item,
            "Provider simulator",
            "recheck_requirements",
            f"Received {m['provider']} message {m['mid']}. Rechecked requirements. "
            "Earlier selections and quotations are historical.",
            store._now(),
        )
    return key


def _process(db, row):
    m = json.loads(row["normalised"])
    key, reason = _associate(db, m)
    if key is not None:
        key = _accept(db, m, key)
    status = "accepted" if key else "held"
    db.execute(
        "UPDATE provider_mail SET status=?,enquiry_id=?,reason=? WHERE id=?",
        (status, key, reason, row["id"]),
    )
    return {"id": row["id"], "status": status, "enquiry_id": key, "reason": reason}


def ingest(path, provider: str, raw: dict) -> dict:
    m = normalise(provider, raw)
    with store._transaction(path, write=True) as db:
        old = db.execute(
            "SELECT * FROM provider_mail WHERE provider=? AND mid=?",
            (provider, m["mid"]),
        ).fetchone()
        if old:
            if m != json.loads(old["normalised"]):
                raise ValueError(
                    "This provider message ID has different content. Original delivery preserved."
                )
            return {
                "id": old["id"],
                "status": "duplicate",
                "enquiry_id": old["enquiry_id"],
                "reason": old["reason"],
            }
        receipt = db.execute(
            """INSERT INTO provider_mail(provider,mid,thread,internet,raw,normalised,status,reason)
                                VALUES(?,?,?,?,?,?,'held','') RETURNING *""",
            (
                provider,
                m["mid"],
                m["thread"],
                m["internet"],
                json.dumps(raw),
                json.dumps(m),
            ),
        ).fetchone()
        return _process(db, receipt)


def retry(path, receipt: int) -> dict:
    with store._transaction(path, write=True) as db:
        row = db.execute(
            "SELECT * FROM provider_mail WHERE id=?", (receipt,)
        ).fetchone()
        if not row:
            raise KeyError(receipt)
        if row["status"] == "held":
            return _process(db, row)
        return {
            "id": receipt,
            "status": "duplicate",
            "enquiry_id": row["enquiry_id"],
            "reason": "",
        }


def deliveries(path) -> list[dict]:
    with store._transaction(path) as db:
        return [
            {**dict(row), "message": json.loads(row["normalised"])}
            for row in db.execute("SELECT * FROM provider_mail ORDER BY id DESC")
        ]


def replay(path, receipt: int) -> dict:
    with store._transaction(path) as db:
        row = db.execute(
            "SELECT provider,raw FROM provider_mail WHERE id=?", (receipt,)
        ).fetchone()
        if not row:
            raise KeyError(receipt)
    return ingest(path, row["provider"], json.loads(row["raw"]))
