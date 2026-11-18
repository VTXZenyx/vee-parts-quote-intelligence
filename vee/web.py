"""Local, synthetic employee workspace. Run with python -m vee.web."""

import hmac
import os
import secrets
import sqlite3
from pathlib import Path
from uuid import uuid4

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.wrappers import Response

from vee import store


def create_app(database: Path | str | None = None) -> Flask:
    app = Flask(__name__)
    path = Path(database or os.environ.get("VEE_DATABASE") or Path(app.instance_path) / "workspace.sqlite3")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    store.init(str(path))
    app.config.update(
        SECRET_KEY=secrets.token_bytes(32),
        SESSION_COOKIE_SAMESITE="Strict",
        MAX_CONTENT_LENGTH=32 * 1024,
        TRUSTED_HOSTS=["localhost", "127.0.0.1", "[::1]"],
    )

    @app.context_processor
    def form_context() -> dict[str, str]:
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        return {"csrf": session["csrf"]}

    @app.after_request
    def response_headers(response: Response) -> Response:
        response.headers.update({
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'self'; object-src 'none'; base-uri 'none'; "
                                       "frame-ancestors 'none'; form-action 'self'",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "same-origin",
        })
        return response

    @app.errorhandler(sqlite3.DatabaseError)
    def database_unavailable(error: sqlite3.DatabaseError) -> tuple[str, int]:
        app.logger.error("Workspace database operation failed (%s)", getattr(error, "sqlite_errorname", "SQLITE_ERROR"))
        return render_template("unavailable.html"), 503

    @app.before_request
    def protect_mutations() -> None:
        if request.method != "POST":
            return
        token = session.get("csrf")
        if not token or not hmac.compare_digest(request.form.get("csrf", "").encode(), token.encode()):
            abort(403)
        if request.headers.get("Origin", request.host_url.rstrip("/")) != request.host_url.rstrip("/"):
            abort(403)

    @app.route("/enquiries/new", methods=["GET", "POST"])
    def new_enquiry() -> Response | str | tuple[str, int]:
        values = request.form
        message_id = values.get("message_id", str(uuid4()))
        if request.method == "POST":
            try:
                key = store.receive(path, values.get("message_id", ""), values.get("customer", ""),
                                    values.get("subject", ""), values.get("body", ""))
            except ValueError as error:
                flash(str(error), "error")
                return render_template("new.html", accounts=store.CUSTOMERS, values=values,
                                       message_id=message_id), 422
            return redirect(url_for("enquiry", id=key), code=303)
        return render_template("new.html", accounts=store.CUSTOMERS, values=values, message_id=message_id)

    @app.get("/")
    def inbox() -> str:
        query = request.args.get("q", "").strip()
        rows = store.inbox(str(path))
        all_rows = rows
        if query:
            rows = [r for r in rows if any(query.casefold() in str(r[k]).casefold()
                    for k in ("id", "customer", "subject"))]
        return render_template("inbox.html", rows=rows, all_rows=all_rows, q=query)

    @app.get("/enquiries/<id>")
    def enquiry(id: str) -> str:
        try:
            item = store.detail(str(path), id)
        except KeyError:
            abort(404)
        return render_template("detail.html", item=item)

    @app.post("/enquiries/<id>/actions")
    def perform(id: str) -> Response:
        try:
            store.act(str(path), id, request.form.get("action", ""), request.form.to_dict())
        except KeyError:
            abort(404)
        except ValueError as error:
            flash(str(error), "error")
        else:
            flash("Changes saved.", "success")
        return redirect(url_for("enquiry", id=id), code=303)

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5050)
