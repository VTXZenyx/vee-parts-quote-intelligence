"""Preview and activate local CSV changes inside an isolated demonstration workspace."""

import sqlite3
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    g,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.wrappers import Response

from vee import catalogue_import as imports
from vee.database import transaction

catalogue_bp = Blueprint("catalogue_import", __name__, url_prefix="/catalogue/import")
SAMPLE = Path(__file__).with_name("fixtures") / "synthetic_catalogue.csv"


@catalogue_bp.before_app_request
def bound_catalogue_upload() -> None:
    if request.endpoint == "catalogue_import.index" and request.method == "POST":
        # The global CSRF check reads request.form, so set limits before that read.
        request.max_content_length = imports.MAX_BYTES + 8192
        request.max_form_parts = 5


def upload_form(error: str = "", status: int = 200, *, show_upload: bool = False) -> tuple[str, int]:
    return render_template(
        "catalogue_import.html", error=error, show_upload=show_upload,
        revision=imports.active_revision(g.database) if g.workspace else 0,
        max_kib=imports.MAX_BYTES // 1024, max_rows=imports.MAX_ROWS,
    ), status


@catalogue_bp.errorhandler(RequestEntityTooLarge)
def oversized(_error: Exception) -> tuple[str, int]:
    return upload_form(f"Upload one CSV file up to {imports.MAX_BYTES // 1024} KiB.", 413, show_upload=True)


@catalogue_bp.errorhandler(sqlite3.DatabaseError)
def database_error(error: sqlite3.DatabaseError) -> tuple[str, int]:
    current_app.logger.error("Catalogue operation failed (%s)", getattr(error, "sqlite_errorname", "SQLITE_ERROR"))
    return render_template("catalogue_import.html", unavailable=True), 503


@catalogue_bp.get("/products")
def products() -> str:
    query = request.args.get("q", "").strip()
    family = request.args.get("family", "")
    with transaction(g.database) as db:
        parts = list(imports.active_parts(db).values())
        revision = imports.published_revision(db)
    families = sorted({part.family for part in parts})
    if family not in families:
        family = ""
    words = query.casefold().split()
    matches = []
    for part in parts:
        if family and part.family != family:
            continue
        description = " ".join((part.sku, part.name, part.family, *part.specs.values())).casefold()
        if all(word in description for word in words):
            matches.append(part)
    return render_template("products.html", parts=sorted(matches, key=lambda p: p.sku),
                           query=query, family=family, families=families, revision=revision)


@catalogue_bp.get("/sample.csv")
def sample() -> Response:
    return send_file(SAMPLE, mimetype="text/csv", as_attachment=True, download_name="synthetic_catalogue.csv")


@catalogue_bp.route("", methods=["GET", "POST"])
def index() -> Response | tuple[str, int]:
    if request.method == "GET":
        return upload_form()
    if not g.workspace:
        return upload_form("Open a catalogue demo before importing a file.", 409)
    source = request.form.get("source")
    try:
        if source == "sample" and not request.files:
            raw = SAMPLE.read_bytes()
        elif source == "file":
            files = list(request.files.items(multi=True))
            if len(files) != 1 or files[0][0] != "file":
                raise ValueError("Choose one CSV file to review.")
            upload = files[0][1]
            if not upload.filename or not upload.filename.lower().endswith(".csv"):
                raise ValueError("Choose a file with a .csv extension.")
            if request.form.get("synthetic") != "yes":
                raise ValueError("Confirm that the file contains only fictional product and pricing data.")
            raw = upload.stream.read(imports.MAX_BYTES + 1)
            if len(raw) > imports.MAX_BYTES:
                raise RequestEntityTooLarge()
        else:
            raise ValueError("Choose the supplied sample or upload a synthetic CSV file.")
        staged = imports.stage(g.database, raw)
    except ValueError as error:
        return upload_form(str(error), 422, show_upload=source == "file")
    return redirect(url_for("catalogue_import.review", stage_id=staged["id"]), code=303)


def _display_fields(record: dict) -> dict[str, str]:
    stock, price = record["stock"], record["price_nzd"]
    return {
        "Name": record["name"],
        "Family": record["family"],
        "Status": record["status"].capitalize(),
        "Stock on hand": "Unknown" if stock is None else str(stock),
        "Net unit price": "Unknown" if price is None else f"NZD {price}",
        **{key.capitalize(): value for key, value in record["specs"].items()},
    }


def _comparison(change: dict) -> list[dict]:
    """Display every field, placing changes first when a record already exists."""
    before = _display_fields(change["before"]) if change["before"] else {}
    after = _display_fields(change["after"])
    rows = []
    for label in dict.fromkeys([*after, *before]):
        old, new = before.get(label, "—"), after.get(label, "—")
        rows.append({"label": label, "old": old, "new": new, "changed": old != new})
    return sorted(rows, key=lambda field: not field["changed"])


def review_page(stage_id: str, error: str = "") -> tuple[str, int]:
    if not g.workspace:
        abort(404)
    try:
        staged = imports.preview(g.database, stage_id)
    except KeyError:
        abort(404)
    except ValueError:
        return upload_form("This saved review could not be read. Return to the original workspace and open "
                           "a fresh catalogue demo to review the file again.", 409)
    status = 200
    if error:
        superseded = staged["active_revision"] != staged["base_revision"]
        status = 409 if staged["activated_revision"] is not None or superseded else 422
    return render_template(
        "catalogue_import.html", review=staged, error=error,
        comparisons={change["sku"]: _comparison(change) for change in staged["changes"]},
    ), status


@catalogue_bp.get("/<stage_id>")
def review(stage_id: str) -> tuple[str, int]:
    return review_page(stage_id)


@catalogue_bp.post("/<stage_id>/activate")
def activate(stage_id: str) -> Response | tuple[str, int]:
    if not g.workspace:
        abort(404)
    try:
        imports.activate(g.database, stage_id, confirmed=request.form.get("confirm") == "yes")
    except KeyError:
        abort(404)
    except ValueError as error:
        return review_page(stage_id, str(error))
    return redirect(url_for("catalogue_import.review", stage_id=stage_id), code=303)
