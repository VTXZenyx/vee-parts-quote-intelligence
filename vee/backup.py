"""Back up or restore a local synthetic VEE workspace to a new SQLite file."""

import argparse
import os
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path

from vee.store import SCHEMA


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
