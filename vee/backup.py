"""Back up or restore a local synthetic VEE workspace to a new SQLite file."""

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path

from vee.store import ALLOWED, SCHEMA


def _verify_snapshot(database: sqlite3.Connection) -> None:
    objects = "SELECT type, name, sql FROM sqlite_schema WHERE name NOT GLOB 'sqlite_*' ORDER BY name"
    database.execute("PRAGMA trusted_schema=OFF")
    with closing(sqlite3.connect(":memory:")) as reference:
        reference.executescript(SCHEMA)
        if database.execute(objects).fetchall() != reference.execute(objects).fetchall():
            raise ValueError("File does not match this version of the VEE workspace schema.")
    if database.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise ValueError("SQLite integrity check failed.")
    if database.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise ValueError("The workspace contains a broken record reference.")


    for key, revision, state in database.execute("SELECT id,revision,state FROM enquiries"):
        item = json.loads(state)
        if not isinstance(item, dict) or item.get("id") != key or item.get("revision") != revision:
            raise ValueError("Enquiry state disagrees with its stored identity or revision.")
        if (not isinstance(item.get("status"), str) or item["status"] not in ALLOWED or not isinstance(item.get("extraction"), dict)
                or not isinstance(item["extraction"].get("lines"), list)
                or not isinstance(item.get("thread"), list) or not item["thread"]
                or not all(isinstance(item.get(field), str) for field in ("customer", "subject", "body", "sender"))):
            raise ValueError("Incomplete enquiry state.")
        audit = database.execute(
            "SELECT count(*),min(revision),max(revision) FROM events WHERE enquiry_id=?", (key,)
        ).fetchone()
        if audit != (revision, 1, revision):
            raise ValueError("Incomplete enquiry audit history.")
        versions = database.execute(
            "SELECT version,snapshot FROM quotes WHERE enquiry_id=? ORDER BY version", (key,)
        )
        count = 0
        for count, (version, snapshot) in enumerate(versions, 1):
            quote = json.loads(snapshot)
            if (not isinstance(quote, dict) or version != count or quote.get("version") != version
                    or not isinstance(quote.get("lines"), list) or not quote["lines"]):
                raise ValueError("Incomplete quotation history.")
        changes = database.execute(
            "SELECT count(*) FROM events WHERE enquiry_id=? AND action IN ('create_quote','edit_quote')", (key,)
        ).fetchone()[0]
        if changes != count or (not count and item["status"] in {"approved", "draft_quote", "rejected"}):
            raise ValueError("Quotation history disagrees with the workflow.")


def _stop_if_busy(status: int, remaining: int, total: int) -> None:
    if status in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
        raise ValueError("Database is busy. Close the local application and retry.")


def copy_workspace(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise ValueError("Select an existing local SQLite workspace or backup file.")
    sidecars = ("-wal", "-shm", "-journal")
    if destination.name.endswith(sidecars) or any(os.path.lexists(str(destination) + ext) for ext in sidecars):
        raise ValueError("Choose a new SQLite filename with no existing journal or WAL files.")
    if os.path.lexists(destination):
        raise FileExistsError(f"Destination already exists: {destination}")
    with tempfile.TemporaryDirectory(prefix=".vee-snapshot-", dir=destination.parent) as staging:
        staged = Path(staging) / "snapshot.sqlite3"
        staged.touch(mode=0o600)
        source_uri = source.resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(source_uri, uri=True)) as original, closing(sqlite3.connect(staged)) as copy:
            original.backup(copy, pages=256, progress=_stop_if_busy)
            copy.execute("PRAGMA journal_mode=DELETE")
            _verify_snapshot(copy)
        # Publishing with a hard link atomically refuses any competing destination.
        os.link(staged, destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("backup", "restore"))
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path, help="new file in an existing local directory")
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
