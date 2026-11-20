"""Review one immutable inbound source at a time, under the enquiry's revision lock."""

import json

from vee import store
from vee.extraction import extract


def sources(item):
    return [entry for entry in item["thread"] if entry["direction"] == "inbound"]


def select(item, source):
    messages = sources(item)
    if source is None:
        source = str(len(messages))
    if source not in {str(i) for i in range(1, len(messages) + 1)}:
        raise ValueError("Choose an existing customer message.")
    message = messages[int(source) - 1]
    identity = message.get("internet") or message.get("message_id") or f"{item['id']} inbound {source}"
    subject = message.get("subject") or (item["subject"] if source == "1" else "")
    return source, identity, subject, message["body"]


def displayed(item, source):
    source, identity, subject, body = select(item, source)
    saved = item.get("advisories", {}).get(source)
    return source, saved or extract(identity, body, subject=subject)


def check_revision(item, revision):
    if str(item["revision"]) != revision:
        raise ValueError("This enquiry has changed. Review the latest revision and retry.")


def process(path, key, fields):
    item = store.detail(path, key)
    check_revision(item, fields.get("revision"))
    source, identity, subject, body = select(item, fields.get("source"))
    # Await the optional external service outside the database write transaction.
    result = extract(identity, body, fields.get("mode", "deterministic"), subject=subject)
    with store._transaction(path, write=True) as db:
        item = store._load(db, key)
        check_revision(item, fields.get("revision"))
        item.setdefault("advisories", {})[source] = result
        detail = f"Message {source} ({identity}): {result['method']} {result['model']}. {result['notice']}"
        store._save_revision(db, item, "Demo employee", "extract_findings", detail, store._now())


def review(path, key, fields):
    with store._transaction(path, write=True) as db:
        item = store._load(db, key)
        check_revision(item, fields.get("revision"))
        source, result = displayed(item, fields.get("source"))
        index = fields.get("finding")
        if index not in {str(i) for i in range(len(result["findings"]))}:
            raise ValueError("Choose a finding from this message.")
        row = result["findings"][int(index)]
        reason = store._text(fields.get("reason"), "the reason for this review")
        decision = fields.get("decision")
        if decision not in {"confirm", "correct"}:
            raise ValueError("Choose a review decision.")
        note = {"decision": decision, "reason": reason, "original": row["value"]}
        action = "review_finding"
        if decision == "correct":
            note["replacement"] = store._text(fields.get("replacement"), "the proposed correction")
            item.setdefault("correction_hold", []).append({"source": source, "finding": index,
                "replacement": note["replacement"], "after": len(sources(item))})
            item.update(selected_skus=[], selected_sku=None)
            store._investigate(item)
            action = "recheck_requirements"
        result.setdefault("reviews", {})[index] = note
        item.setdefault("advisories", {})[source] = result
        audit = {"source": result["source"], "method": result["method"], "finding": row, **note}
        store._save_revision(db, item, "Demo employee", action, json.dumps(audit, ensure_ascii=False), store._now())
