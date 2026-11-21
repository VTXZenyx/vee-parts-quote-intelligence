"""Staged synthetic CSV patches. The active catalogue belongs to one SQLite workspace."""

import csv
import hashlib
import io
import re
import sqlite3
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from vee.catalogue import BY_SKU, PREFIXES, Part, Record
from vee.database import transaction

MAX_BYTES = 65_536
MAX_ROWS = 100
HEADER = ("sku", "family", "name", "specs", "status", "stock", "price_nzd")
KINDS = ("added", "updated", "retired", "unchanged")
IMPORT_SCHEMA = """
CREATE TABLE IF NOT EXISTS catalogue_imports (
    id TEXT PRIMARY KEY NOT NULL,
    base_revision INTEGER NOT NULL CHECK(base_revision >= 0),
    digest TEXT NOT NULL,
    payload BLOB NOT NULL,
    activated_revision INTEGER UNIQUE CHECK(activated_revision = base_revision + 1),
    UNIQUE(base_revision, digest)
);
"""

# Imported specifications use the same unit strings and vocabulary as the matcher.
FAMILY_FIELDS = {
    "Bearing": {"bore", "outside diameter", "width", "closure"},
    "Pneumatic cylinder": {"bore", "stroke", "action", "standard", "port", "mount"},
    "Fastener": {"thread", "length", "pitch", "grade"},
    "Hydraulic adapter": {"thread", "size", "pressure", "connection"},
}
OPTIONS = {
    "closure": {"rubber seals", "metal shields"},
    "action": {"double acting", "single acting"},
    "standard": {"ISO 15552"},
    "port": {"G1/8", "G1/4"},
    "mount": {"foot mount", "clevis mount", "flange mount"},
    "grade": {"8.8", "10.9"},
    "size": {"1/4 in", "3/8 in", "1/2 in"},
    "connection": {"male to male", "female to female", "male to female"},
}


def _specs(text: str, family: str) -> dict[str, str]:
    specs: dict[str, str] = {}
    for field in text.split(";"):
        key, sep, value = (s.strip() for s in field.partition("="))
        if not sep or key in specs or key not in FAMILY_FIELDS[family]:
            raise ValueError(f"Invalid or repeated specification for {family}.")
        choices = OPTIONS.get(key)
        if key == "thread":
            choices = {"M12"} if family == "Fastener" else {"BSPP", "BSPT", "NPT"}
        if choices:
            if value not in choices:
                raise ValueError(
                    f"Unsupported {key}. Choose from {', '.join(sorted(choices))}."
                )
        else:
            unit = "bar" if key == "pressure" else "mm"
            match = re.fullmatch(r"([0-9]{1,5}(?:\.[0-9]{1,3})?) " + unit, value)
            if not match or Decimal(match[1]) <= 0:
                raise ValueError(f"Enter a positive {key} in {unit}.")
            value = f"{Decimal(match[1]).normalize():f} {unit}"
        specs[key] = value
    missing = FAMILY_FIELDS[family] - specs.keys()
    if missing:
        raise ValueError(f"Missing specifications: {', '.join(sorted(missing))}.")
    if family == "Bearing" and Decimal(specs["outside diameter"].split()[0]) <= Decimal(
        specs["bore"].split()[0]
    ):
        raise ValueError("Bearing outside diameter must exceed its bore.")
    return specs


def _part(row: list[str]) -> Part:
    if len(row) != len(HEADER) or any(
        not value.isprintable() for value in row if value
    ):
        raise ValueError("Use seven single-line fields with printable text.")
    sku, family, name, specifications, status, stock, price = (v.strip() for v in row)
    if not re.fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)+", sku) or len(sku) > 48:
        raise ValueError(
            "Use an uppercase, hyphen-separated SKU of up to 48 characters."
        )
    if family not in FAMILY_FIELDS or PREFIXES.get(sku.split("-", 1)[0]) != family:
        raise ValueError("The SKU prefix must match a supported product family.")
    if (
        not 1 <= len(name) <= 120
        or name.startswith(("=", "+", "-", "@"))
        or '"' in name
    ):
        raise ValueError("Enter a plain product name of up to 120 characters.")
    if status not in {"active", "discontinued"}:
        raise ValueError("Status must be active or discontinued.")
    if stock and not re.fullmatch(r"[0-9]{1,6}", stock):
        raise ValueError(
            "Use blank for unknown stock or a whole number from 0 to 999999."
        )
    if price and not re.fullmatch(r"[0-9]{1,8}(?:\.[0-9]{1,2})?", price):
        raise ValueError(
            "Use blank for unknown pricing or a non-negative NZD amount with at most two decimal places."
        )
    return Part(
        sku,
        family,
        name,
        _specs(specifications, family),
        int(stock) if stock else None,
        format(Decimal(price), ".2f") if price else None,
        status == "discontinued",
    )


def parse_csv(raw: bytes) -> list[Part]:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("Choose a non-empty CSV file of at most 64 KiB.")
    try:
        source = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Save the CSV in UTF-8 encoding.") from error
    reader = csv.reader(io.StringIO(source, newline=""), strict=True)
    parts: list[Part] = []
    seen: set[str] = set()
    try:
        if next(reader, []) != list(HEADER):
            raise ValueError(f"Use the exact CSV header: {','.join(HEADER)}.")
        for row in reader:
            if len(parts) >= MAX_ROWS:
                raise ValueError(f"Import at most {MAX_ROWS} products per file.")
            try:
                part = _part(row)
                if part.sku in seen:
                    raise ValueError(f"Duplicate SKU {part.sku}.")
            except ValueError as error:
                raise ValueError(f"Row {reader.line_num}: {error}") from error
            seen.add(part.sku)
            parts.append(part)
    except csv.Error as error:
        raise ValueError(f"Invalid CSV quoting near row {reader.line_num}.") from error
    if not parts:
        raise ValueError("Include at least one product row.")
    return parts


def _reviewed_products(raw: bytes, digest: str) -> list[Part]:
    if (
        type(raw) is not bytes
        or not 0 < len(raw) <= MAX_BYTES
        or hashlib.sha256(raw).hexdigest() != digest
    ):
        raise ValueError("The saved import differs from the reviewed file.")
    return parse_csv(raw)


def _fields(part: Part) -> Record:
    return {
        "sku": part.sku,
        "family": part.family,
        "name": part.name,
        "specs": dict(part.specs),
        "status": "discontinued" if part.discontinued else "active",
        "stock": part.stock,
        "price_nzd": part.price,
    }


def _changes(current: dict[str, Part], products: list[Part]) -> list[Record]:
    changes = []
    for part in products:
        old = current.get(part.sku)
        if old is None:
            if part.discontinued:
                raise ValueError(f"Cannot retire unknown SKU {part.sku}.")
            kind = "added"
        elif old == replace(part, revision=old.revision):
            kind = "unchanged"
        elif not old.discontinued and part.discontinued:
            kind = "retired"
        else:
            kind = "updated"
        changes.append(
            {
                "kind": kind,
                "sku": part.sku,
                "before": _fields(old) if old else None,
                "after": _fields(part),
            }
        )
    return changes


def published_revision(db: sqlite3.Connection) -> int:
    return db.execute(
        "SELECT coalesce(max(activated_revision),0) FROM catalogue_imports"
    ).fetchone()[0]


def active_parts(db: sqlite3.Connection, through: int | None = None) -> dict[str, Part]:
    """Read the immutable published patches inside the caller's transaction."""
    current = BY_SKU.copy()
    query = """SELECT activated_revision,payload,digest FROM catalogue_imports
               WHERE activated_revision <= ? ORDER BY activated_revision"""
    for revision, raw, digest in db.execute(
        query, (through if through is not None else published_revision(db),)
    ):
        for part in _reviewed_products(raw, digest):
            old = current.get(part.sku)
            if old is None or old != replace(part, revision=old.revision):
                current[part.sku] = replace(part, revision=revision)
    return current


def active_revision(path: str | Path) -> int:
    with transaction(path) as db:
        return published_revision(db)


def _preview(db: sqlite3.Connection, stage_id: str) -> Record:
    row = db.execute(
        "SELECT base_revision,activated_revision,payload,digest FROM catalogue_imports WHERE id=?",
        (stage_id,),
    ).fetchone()
    if row is None:
        raise KeyError(stage_id)
    base, published, raw, digest = row
    changes = _changes(active_parts(db, base), _reviewed_products(raw, digest))
    counts = {kind: sum(row["kind"] == kind for row in changes) for kind in KINDS}
    if counts["unchanged"] == len(changes):
        raise ValueError("This file has no catalogue changes to activate.")
    return {
        "id": stage_id,
        "base_revision": base,
        "active_revision": published_revision(db),
        "activated_revision": published,
        "changes": changes,
        "counts": counts,
    }


def stage(path: str | Path, raw: bytes) -> Record:
    parse_csv(raw)
    digest = hashlib.sha256(raw).hexdigest()
    with transaction(path, write=True) as db:
        base = published_revision(db)
        if db.execute(
            "SELECT 1 FROM catalogue_imports WHERE digest=? AND activated_revision IS NOT NULL",
            (digest,),
        ).fetchone():
            raise ValueError("This exact CSV file was already activated.")
        previous = db.execute(
            "SELECT id FROM catalogue_imports WHERE base_revision=? AND digest=?",
            (base, digest),
        ).fetchone()
        stage_id = previous[0] if previous else uuid4().hex
        if previous is None:
            db.execute(
                "INSERT INTO catalogue_imports(id,base_revision,digest,payload) VALUES (?,?,?,?)",
                (stage_id, base, digest, raw),
            )
        return _preview(db, stage_id)


def preview(path: str | Path, stage_id: str) -> Record:
    with transaction(path) as db:
        return _preview(db, stage_id)


def activate(path: str | Path, stage_id: str, *, confirmed: bool) -> int:
    if confirmed is not True:
        raise ValueError("Explicitly confirm activation of this reviewed revision.")
    with transaction(path, write=True) as db:
        result = _preview(db, stage_id)
        if result["activated_revision"] is not None:
            raise ValueError("This revision was already activated.")
        if result["active_revision"] != result["base_revision"]:
            raise ValueError(
                "This review is stale. Upload the file again to compare it with the current revision."
            )
        revision = result["base_revision"] + 1
        db.execute(
            "UPDATE catalogue_imports SET activated_revision=? WHERE id=?",
            (revision, stage_id),
        )
        return revision


def verify_history(db: sqlite3.Connection) -> None:
    """Replay each base once, validating its pending patches before its activated patch."""
    current = BY_SKU.copy()
    revision = 0
    query = """SELECT id,base_revision,activated_revision,payload,digest FROM catalogue_imports
               ORDER BY base_revision, activated_revision IS NOT NULL"""
    for stage_id, base, activated, raw, digest in db.execute(query):
        if (
            not isinstance(stage_id, str)
            or not re.fullmatch("[a-f0-9]{32}", stage_id)
            or type(base) is not int
            or base != revision
            or (activated is not None and activated != base + 1)
        ):
            raise ValueError("Invalid catalogue import identity or revision.")
        products = _reviewed_products(raw, digest)
        changes = _changes(current, products)
        if all(change["kind"] == "unchanged" for change in changes):
            raise ValueError("A saved import contains no catalogue changes.")
        if activated is not None:
            revision = activated
            for product, change in zip(products, changes):
                if change["kind"] != "unchanged":
                    current[product.sku] = replace(product, revision=revision)
