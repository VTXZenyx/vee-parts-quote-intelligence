"""Back up or restore a local synthetic VEE workspace to a new SQLite file."""

import argparse
import json
import os
import re
import sqlite3
import sys
import tempfile
from contextlib import closing
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from vee.provider_mail import normalise
from vee.store import ALLOWED, SCHEMA, V2_SCHEMA


def _fields(value: object, **schema: type) -> dict:
    if not isinstance(value, dict) or any(
        type(value.get(key)) is not kind for key, kind in schema.items()
    ):
        raise ValueError(
            "A saved record is missing a required field or has an invalid field type."
        )
    return value


def _decimal(value: object) -> Decimal:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,16}\.[0-9]{2}", value):
        raise ValueError("A quotation contains an invalid financial value.")
    return Decimal(value)


def _verify_quote(version: int, raw: str) -> str:
    quote = _fields(
        json.loads(raw),
        version=int,
        lines=list,
        currency=str,
        notes=str,
        created_at=str,
    )
    if quote["version"] != version or quote["currency"] != "NZD" or not quote["lines"]:
        raise ValueError("Invalid quotation identity, currency or line list.")
    subtotal = Decimal("0.00")
    skus: set[str] = set()
    for value in quote["lines"]:
        line = _fields(
            value, sku=str, name=str, quantity=int, unit_price=str, line_total=str
        )
        if not line["sku"] or line["sku"] in skus or not 1 <= line["quantity"] <= 9999:
            raise ValueError("Invalid or repeated quotation line.")
        skus.add(line["sku"])
        extended = _decimal(line["unit_price"]) * line["quantity"]
        if _decimal(line["line_total"]) != extended:
            raise ValueError(
                "A quotation line total differs from its historical quantity and price."
            )
        subtotal += extended
    rate = _decimal(quote.get("gst_rate"))
    tax = (subtotal * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if (
        rate > 1
        or subtotal != _decimal(quote.get("subtotal"))
        or tax != _decimal(quote.get("gst"))
        or subtotal + tax != _decimal(quote.get("total"))
    ):
        raise ValueError(
            "Quotation totals do not reconcile with the saved lines and tax rate."
        )
    if any(
        quote.get(key) != quote["lines"][0][key]
        for key in ("sku", "unit_price", "quantity")
    ):
        raise ValueError("The quotation summary disagrees with its first line.")
    return f"quotation version {version} for {quote['currency']} {quote['total']}"


def _verify_enquiry(raw: str, key: str, revision: int) -> dict:
    state = _fields(
        json.loads(raw),
        id=str,
        revision=int,
        status=str,
        customer=str,
        subject=str,
        sender=str,
        received_at=str,
        body=str,
        thread=list,
        sample_reply=str,
        attachments=list,
        selected_skus=list,
        clarification=str,
        extraction=dict,
    )
    if (
        state["id"] != key
        or state["revision"] != revision
        or state["status"] not in ALLOWED
    ):
        raise ValueError("Enquiry identity, revision or workflow status is invalid.")
    if not state["thread"]:
        raise ValueError("An enquiry lacks its original message.")
    for message in state["thread"]:
        _fields(message, author=str, at=str, direction=str, body=str)
        if message["direction"] not in {"inbound", "outbound"}:
            raise ValueError("Invalid message direction.")
    for attachment in state["attachments"]:
        _fields(attachment, name=str, text=str)
    analysis = _fields(
        state["extraction"], lines=list, questions=list, urgent=bool, ready=bool
    )
    if not analysis["lines"]:
        raise ValueError("The saved enquiry contains no requirement lines.")
    matched = []
    for line in analysis["lines"]:
        _fields(
            line,
            status=str,
            family=str,
            attributes=dict,
            candidates=list,
            issues=list,
            questions=list,
        )
        for candidate in line["candidates"]:
            _fields(candidate, sku=str, name=str, specs=dict, source=str, evidence=list)
        for name, kind in (("sku", str), ("reference", str), ("quantity", int)):
            if name not in line or (
                line[name] is not None and type(line[name]) is not kind
            ):
                raise ValueError(
                    "A saved requirement has an invalid or missing decision field."
                )
        if line["status"] == "verified":
            if (
                not line["sku"]
                or not line["quantity"]
                or line["quantity"] < 1
                or sum(
                    candidate["sku"] == line["sku"] for candidate in line["candidates"]
                )
                != 1
            ):
                raise ValueError(
                    "A matched line lacks a quantity or a unique saved catalogue candidate."
                )
            matched.append(line["sku"])
        elif line["sku"] is not None or line["status"] not in {
            "review",
            "conflict",
            "clarify",
        }:
            raise ValueError("An unresolved requirement has an invalid decision.")
    ready = len(matched) == len(analysis["lines"]) and not any(
        line["issues"] for line in analysis["lines"]
    )
    if analysis["ready"] != ready:
        raise ValueError("Enquiry readiness disagrees with the saved requirements.")
    reviewed = state["status"] in {"verified", "draft_quote", "rejected", "approved"}
    if reviewed and (
        not ready
        or state["selected_skus"] != matched
        or state.get("selected_sku") != matched[0]
    ):
        raise ValueError(
            "The employee selection disagrees with the technically resolved lines."
        )
    return state


def _verify_history(database: sqlite3.Connection, key: str, state: dict) -> None:
    events = database.execute(
        "SELECT revision, action, detail FROM events WHERE enquiry_id=? ORDER BY revision",
        (key,),
    ).fetchall()
    if (
        not events
        or events[0][1] != "received"
        or len(events) != state["revision"]
        or any(
            revision != expected for expected, (revision, _, _) in enumerate(events, 1)
        )
    ):
        raise ValueError("The enquiry and its audit revisions do not reconcile.")
    quotes = database.execute(
        "SELECT version,snapshot FROM quotes WHERE enquiry_id=? ORDER BY version",
        (key,),
    )
    version = 0
    quote_reference = ""
    approved = False
    for _, action, detail in events:
        if action == "recheck_requirements":
            approved = False
        elif approved:
            raise ValueError(
                "An approved enquiry changed without a requirements recheck."
            )
        elif action in {"create_quote", "edit_quote"}:
            version += 1
            row = quotes.fetchone()
            if row is None or row[0] != version:
                raise ValueError("A saved quotation version is missing.")
            quote_reference = _verify_quote(version, row[1])
            if detail != f"Saved {quote_reference} including GST.":
                raise ValueError(
                    "The recorded save decision disagrees with the historical quote."
                )
        elif action == "approve_quote":
            if not version or detail != f"Employee approved {quote_reference}.":
                raise ValueError(
                    "The recorded approval disagrees with the historical quote."
                )
            approved = True
    if quotes.fetchone() is not None:
        raise ValueError("A quotation version has no corresponding save event.")
    final_actions = {
        "verified": {"verify_match"},
        "draft_quote": {"create_quote", "edit_quote"},
        "approved": {"approve_quote"},
        "rejected": {"reject_quote"},
        "awaiting_reply": {"approve_clarification"},
    }
    status = state["status"]
    if status in final_actions and events[-1][1] not in final_actions[status]:
        raise ValueError("The current state lacks its corresponding audit decision.")
    if approved != (status == "approved") or (
        status in {"rejected", "draft_quote"} and not version
    ):
        raise ValueError(
            "Quotation approval history and workflow state do not reconcile."
        )


def _verify_snapshot(database: sqlite3.Connection) -> None:
    objects = "SELECT type, name, sql FROM sqlite_schema WHERE name NOT GLOB 'sqlite_*' ORDER BY name"
    database.execute("PRAGMA trusted_schema=OFF")
    with closing(sqlite3.connect(":memory:")) as reference:
        version = database.execute("PRAGMA user_version").fetchone()[0]
        reference.executescript(V2_SCHEMA if version < 3 else SCHEMA)
        if (
            database.execute(objects).fetchall()
            != reference.execute(objects).fetchall()
        ):
            raise ValueError(
                "File does not match this version of the VEE workspace schema."
            )
    if database.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise ValueError("SQLite integrity check failed.")
    if database.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise ValueError("The workspace contains a broken record reference.")
    if database.execute(
        "SELECT 1 FROM events WHERE enquiry_id IS NULL UNION ALL "
        "SELECT 1 FROM quotes WHERE enquiry_id IS NULL LIMIT 1"
    ).fetchone():
        raise ValueError("An audit event or quote lacks its owning enquiry.")
    sources: dict[tuple[str, str], tuple[str, dict]] = {}
    for key, revision, raw in database.execute(
        "SELECT id,revision,state FROM enquiries"
    ):
        state = _verify_enquiry(raw, key, revision)
        _verify_history(database, key, state)
        for message in state["thread"]:
            if "provider" in message:
                identity = (message["provider"], message["mid"])
                if identity in sources:
                    raise ValueError("Duplicate provider identity in source history.")
                sources[identity] = (key, message)
    if version >= 3:
        for provider, mid, thread, internet, raw, saved, key in database.execute(
            "SELECT provider,mid,thread,internet,raw,normalised,enquiry_id FROM provider_mail"
        ):
            source = normalise(provider, json.loads(raw))
            if (source != json.loads(saved)
                    or (mid, thread, internet) != (source["mid"], source["thread"], source["internet"])):
                raise ValueError("Provider receipt disagrees with its original envelope.")
            if key:
                owner, message = sources.pop((provider, mid), (None, {}))
                if owner != key or any(message.get(k) != source[k] for k in
                                       ("body", "at", "internet", "sender", "recipient", "subject", "attachments")):
                    raise ValueError("Provider receipt disagrees with its enquiry source history.")
    if sources:
        raise ValueError("A message in source history lacks its provider receipt.")


def _stop_if_busy(status: int, remaining: int, total: int) -> None:
    if status in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
        raise ValueError("Database is busy. Close the local application and retry.")


def copy_workspace(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise ValueError("Select an existing local SQLite workspace or backup file.")
    sidecars = ("-wal", "-shm", "-journal")
    if destination.name.endswith(sidecars) or any(
        os.path.lexists(str(destination) + ext) for ext in sidecars
    ):
        raise ValueError(
            "Choose a new SQLite filename with no existing journal or WAL files."
        )
    if os.path.lexists(destination):
        raise FileExistsError(f"Destination already exists: {destination}")
    with tempfile.TemporaryDirectory(
        prefix=".vee-snapshot-", dir=destination.parent
    ) as staging:
        staged = Path(staging) / "snapshot.sqlite3"
        staged.touch(mode=0o600)
        source_uri = source.resolve().as_uri() + "?mode=ro"
        with (
            closing(sqlite3.connect(source_uri, uri=True)) as original,
            closing(sqlite3.connect(staged)) as copy,
        ):
            original.backup(copy, pages=256, progress=_stop_if_busy)
            copy.execute("PRAGMA journal_mode=DELETE")
            _verify_snapshot(copy)
        # Publishing with a hard link atomically refuses any competing destination.
        os.link(staged, destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("backup", "restore"))
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "destination", type=Path, help="new file in an existing local directory"
    )
    args = parser.parse_args()
    try:
        copy_workspace(args.source, args.destination)
    except (sqlite3.Error, OSError, ValueError) as error:
        print(f"{args.operation} failed: {error}", file=sys.stderr)
        return 1
    print(f"Verified {args.operation} written to {args.destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
