"""Local, synthetic employee workspace. Run with python -m vee.web."""

import hmac
import os
import secrets
import sqlite3
from pathlib import Path
from uuid import UUID, uuid4

from flask import (
    Flask,
    abort,
    flash,
    g,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.exceptions import Forbidden
from werkzeug.wrappers import Response

from vee import customer, demo, findings, provider_mail, store
from vee.catalogue import partial_offer
from vee.catalogue_web import catalogue_bp
from vee.extraction import live_enabled

WORKSPACE_COOKIE = "vee_demo_workspace"


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

    app.register_blueprint(catalogue_bp)
    app.register_blueprint(customer.make_blueprint(path))

    workspace_folder = path.parent / f"{path.name}.demos"

    def csrf_token() -> str:
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        token = session["csrf"]
        if g.workspace:
            return hmac.digest(token.encode(), g.workspace.encode(), "sha256").hex()
        return token

    def active_guide() -> dict | None:
        guide = session.get("guide")
        return guide if guide and guide["workspace"] == g.workspace else None

    @app.context_processor
    def form_context() -> dict:
        guide = active_guide()
        title = demo.SHOWCASE[guide.get("scenario", "cylinder")].title if guide else ""
        return {"csrf": csrf_token(), "demo_workspace": g.workspace, "guide": guide, "guide_title": title}

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

    @app.errorhandler(413)
    def form_too_large(_error: Exception) -> tuple[str, int]:
        return render_template("form_too_large.html"), 413

    @app.errorhandler(404)
    def page_missing(_error: Exception) -> tuple[str, int]:
        return render_template("not_found.html"), 404

    @app.errorhandler(403)
    def expired_form(error: Forbidden) -> tuple[str, int]:
        return render_template("form_expired.html"), error.code or 403

    @app.before_request
    def select_workspace() -> None:
        g.workspace = ""
        g.database = path
        selected = request.cookies.get(WORKSPACE_COOKIE)
        if selected:
            try:
                identifier = UUID(selected)
            except ValueError:
                return
            candidate = workspace_folder / f"{identifier.hex}.sqlite3"
            if identifier.version == 4 and selected == identifier.hex and candidate.is_file():
                g.workspace = identifier.hex
                g.database = candidate
                # A saved V2 demo cookie may reopen an older workspace after upgrading.
                with store._transaction(candidate) as db:
                    version = db.execute("PRAGMA user_version").fetchone()[0]
                if version < store.SCHEMA_VERSION:
                    store.init(candidate)

    @app.before_request
    def protect_mutations() -> None:
        if request.method != "POST":
            return
        if not session.get("csrf") or not hmac.compare_digest(
            request.form.get("csrf", "").encode(), csrf_token().encode()
        ):
            abort(403)
        if request.headers.get("Origin", request.host_url.rstrip("/")) != request.host_url.rstrip("/"):
            abort(403)

    @app.get("/showcase")
    def showcase() -> str:
        return render_template("showcase.html", showcase=demo.SHOWCASE, scenarios=demo.SCENARIOS)

    @app.post("/demo-workspace/start")
    def start_demo() -> Response:
        scenario = request.form.get("scenario", "cylinder")
        if scenario not in demo.SHOWCASE:
            abort(400)
        workspace_folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        identifier = uuid4().hex
        fresh = workspace_folder / f"{identifier}.sqlite3"
        fresh.touch(mode=0o600, exist_ok=False)
        store.init(fresh)
        session.pop("guide", None)
        if request.form.get("guided") == "1":
            session["guide"] = {"workspace": identifier, "enquiry": "", "scenario": scenario}
        destination = url_for("demo_email", scenario=scenario)
        if request.form.get("destination") == "catalogue":
            destination = url_for("catalogue_import.index")
        response = make_response(redirect(destination, code=303))
        response.set_cookie(WORKSPACE_COOKIE, identifier, httponly=True, samesite="Strict")
        flash("Fresh demo workspace ready.", "success")
        return response

    @app.post("/demo-workspace/exit-guide")
    def exit_guide() -> Response:
        guide = active_guide()
        session.pop("guide", None)
        address = url_for("enquiry", id=guide["enquiry"]) if guide and guide["enquiry"] else url_for("demo_email")
        return redirect(address, code=303)

    @app.post("/demo-workspace/original")
    def original_workspace() -> Response:
        session.pop("guide", None)
        response = make_response(redirect(url_for("inbox"), code=303))
        response.delete_cookie(WORKSPACE_COOKIE)
        flash("You’re back in the original workspace.", "success")
        return response

    @app.route("/demo-email", methods=["GET", "POST"])
    def demo_email() -> Response | str | tuple[str, int]:
        reply_to = (request.form if request.method == "POST" else request.args).get("reply_to") or None
        item = None
        if reply_to:
            try:
                item = store.detail(g.database, reply_to)
            except KeyError:
                abort(404)

        view = request.args.get("view")
        if request.method != "GET" or item or view not in {"providers", "history"}:
            view = "compose"
        values = {
            "sender": "", "recipient": store.DEMO_RECIPIENT, "subject": "", "body": "", "customer": "",
            "message_id": str(uuid4()), "revision": "",
        }
        if item:
            values.update(store.reply_envelope(item), revision=str(item["revision"]))
            example = demo.REPLY_EXAMPLES.get(request.args.get("reply_example", ""))
            values["body"] = example[1] if example else (item["sample_reply"] or "")
        else:
            scenario = demo.SCENARIOS.get(request.args.get("scenario", ""))
            if scenario:
                values.update(customer=scenario.customer, sender=scenario.sender, subject=scenario.subject,
                              body=scenario.body)

        status = 200
        if request.method == "POST":
            values = {key: request.form.get(key, "") for key in values}
            try:
                key, repeated = store.receive_demo_email(
                    g.database, values["message_id"], values["customer"], values["sender"], values["recipient"],
                    values["subject"], values["body"], enquiry_id=reply_to, revision=values["revision"],
                )
            except ValueError as error:
                flash(str(error), "error")
                status = 422
            else:
                guide = active_guide()
                prepared = demo.SCENARIOS[guide.get("scenario", "cylinder")] if guide else None
                if guide and prepared and not guide["enquiry"] and not reply_to and all(
                    values[field].strip() == getattr(prepared, field)
                    for field in ("customer", "sender", "subject", "body")
                ):
                    session["guide"] = {**guide, "enquiry": key}
                if repeated:
                    message = f"This email was already saved in {key}. The conversation contains one copy."
                elif reply_to:
                    message = "Customer replied. Review the updated request and next step."
                else:
                    message = f"Email saved as {key}. Review the customer’s request."
                flash(message, "success")
                return redirect(url_for("enquiry", id=key), code=303)
        elif item and item["status"] != "awaiting_reply" and not store.accepts_revision(item):
            flash("Approve a question in the enquiry before adding a customer reply.", "error")
            return redirect(url_for("enquiry", id=item["id"]), code=303)

        deliveries = []
        waiting = []
        if view == "history":
            deliveries = sorted(
                ((row, message) for row in store.inbox(g.database)
                 for message in row["thread"] if message.get("message_id")),
                key=lambda entry: entry[1]["at"], reverse=True,
            )
        elif view == "compose":
            waiting = [row for row in store.queue_summaries(g.database) if row["status"] == "awaiting_reply"]
        return render_template(
            "demo_email.html", values=values, item=item, view=view, scenarios=demo.SCENARIOS, reply_examples=demo.REPLY_EXAMPLES,
            deliveries=deliveries, waiting=waiting,
            accounts=store.CUSTOMERS, fixtures=provider_mail.FIXTURES,
            receipts=provider_mail.deliveries(g.database) if view == "providers" else [],
        ), status

    @app.post("/demo-email/providers")
    @app.post("/demo-email/providers/<int:receipt>/<operation>")
    def provider_delivery(receipt: int | None = None, operation: str = "import") -> Response:
        try:
            if receipt is None:
                fixture = provider_mail.FIXTURES.get(request.form.get("fixture", ""))
                if not fixture:
                    raise ValueError("Choose a Gmail or Outlook example.")
                result = provider_mail.ingest(g.database, fixture["provider"], fixture["message"])
            elif operation == "retry":
                result = provider_mail.retry(g.database, receipt)
            elif operation == "replay":
                result = provider_mail.replay(g.database, receipt)
            else:
                abort(404)
        except KeyError:
            abort(404)
        except ValueError as error:
            flash("Rejected. " + str(error), "error")
        else:
            if result["status"] == "duplicate":
                flash("Duplicate email recognised. The original was kept and the enquiry was processed only once."
                      if result["enquiry_id"] else "Duplicate email recognised. The original is still waiting for review.", "success")
            elif result["status"] == "held":
                flash(f"This email needs review. {result['reason']}", "error")
            else:
                flash(f"Email added to {result['enquiry_id']}.", "success")
        return redirect(url_for("demo_email", view="providers"), code=303)

    @app.post("/demo-email/<message_id>/replay")
    def replay_email(message_id: str) -> Response:
        try:
            key, _ = store.replay_demo_email(g.database, message_id)
        except (KeyError, ValueError):
            abort(404)
        flash(f"Duplicate delivery recognised for {key}. No new enquiry or message was created.", "success")
        return redirect(url_for("demo_email", view="history"), code=303)

    @app.route("/enquiries/new", methods=["GET", "POST"])
    def new_enquiry() -> Response | str | tuple[str, int]:
        values = request.form
        message_id = values.get("message_id", str(uuid4()))
        if request.method == "POST":
            try:
                key, repeated = store.receive_enquiry(
                    g.database, values.get("message_id", ""), values.get("customer", ""),
                    values.get("subject", ""), values.get("body", ""),
                )
            except ValueError as error:
                flash(str(error), "error")
                return render_template("new.html", accounts=store.CUSTOMERS, values=values,
                                       message_id=message_id), 422
            flash(f"This enquiry was already saved as {key}. Opening the existing record."
                  if repeated else f"Enquiry {key} saved.", "success")
            return redirect(url_for("enquiry", id=key), code=303)
        return render_template("new.html", accounts=store.CUSTOMERS, values=values, message_id=message_id)

    @app.get("/")
    def inbox() -> str:
        query = request.args.get("q", "").strip()
        rows = store.queue_summaries(g.database)
        all_rows = rows
        if query:
            rows = [r for r in rows if any(query.casefold() in str(r[k]).casefold()
                    for k in ("id", "customer", "subject"))]
        return render_template("inbox.html", rows=rows, all_rows=all_rows, q=query, showcase=demo.SHOWCASE)

    @app.get("/enquiries/<id>")
    def enquiry(id: str) -> str:
        try:
            item = store.detail(g.database, id)
        except KeyError:
            abort(404)
        try:
            source, advisory = findings.displayed(g.database, item, request.args.get("source"))
        except ValueError as error:
            flash(str(error), "error")
            source, advisory = "", None
        body = demo.prepared_reply(active_guide(), item)
        reply = {**store.reply_envelope(item), "body": body, "message_id": str(uuid4())} if body else None
        excess = (store.quantity_increases(item["extraction"], item["quotes"][-1])
                  if item["status"] == "draft_quote" else [])
        return render_template("detail.html", item=item, advisory=advisory, source=source, prepared_reply=reply,
                               quantity_increases=excess,
                               partial=partial_offer(item["extraction"]), inbound=findings.sources(item), live_enabled=live_enabled())

    @app.get("/enquiries/<id>/customer-preview")
    def customer_preview(id: str) -> str | tuple[str, int]:
        try:
            item = store.detail(g.database, id)
        except KeyError:
            abort(404)
        version = request.args.get("version")
        if not customer.current_approved(item, version):
            return render_template("preview_unavailable.html", item=item), 409
        return render_template("customer_preview.html", item=item, preview=True)

    @app.post("/enquiries/<id>/findings")
    @app.post("/enquiries/<id>/findings/<operation>")
    def review_findings(id: str, operation: str = "process") -> Response:
        fields = request.form.to_dict()
        try:
            if operation == "process":
                findings.process(g.database, id, fields)
            elif operation == "review":
                findings.review(g.database, id, fields)
            else:
                abort(404)
        except KeyError:
            abort(404)
        except ValueError as error:
            flash(str(error), "error")
        else:
            flash("Findings saved to enquiry history.", "success")
        return redirect(url_for("enquiry", id=id, source=fields.get("source"), _anchor="findings"), code=303)

    @app.post("/enquiries/<id>/actions")
    def perform(id: str) -> Response:
        try:
            action = request.form.get("action", "")
            item = store.act(g.database, id, action, request.form.to_dict())
        except KeyError:
            abort(404)
        except ValueError as error:
            flash(str(error), "error")
        else:
            messages = {
                "request_quantity_confirmation": "Quantity question saved in the demo inbox. Waiting for the customer’s reply.",
                "approve_clarification": "Question saved in the demo inbox. Waiting for customer reply.",
                "save_clarification": "Changes saved to the customer question.",
                "verify_match": "Product confirmed. You can now prepare the quote.",
                "verify_partial": "Available stock confirmed for a partial quote.",
                "simulate_reply": "Customer replied. Review the new details.",
                "reconcile_requirements": "Updated request confirmed. Check the products again.",
                "reject_quote": "Quotation returned for revision.",
                "refresh_evidence": "Stock, prices and part specifications checked again.",
            }
            if action in {"create_quote", "edit_quote", "approve_quote"}:
                latest = item["quotes"][-1]
                decision = "approved" if action == "approve_quote" else "saved as a draft"
                message = f"Quotation version {latest['version']} {decision} · {latest['currency']} {latest['total']}."
            else:
                message = messages.get(action, "Changes saved to this enquiry.")
            flash(message, "success")
        return redirect(url_for("enquiry", id=id), code=303)

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5050)
