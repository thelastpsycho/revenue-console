"""OAuth 2.1 authorization-code + PKCE endpoints, so MCP clients (e.g. claude.ai's
remote connector) get a real "Sign in" instead of pasting a personal API key into
a request header. Protocol endpoints (/.well-known/*, /oauth/*) are deliberately
outside /api/ so security.py's secure_api() (which only guards /api/*) doesn't
block them - they must be reachable before login, by spec. The token this
ultimately mints is a row in mcp_keys (see accounts.mcp_keys.create_oauth_key) -
nothing elsewhere in the app needs a new way to check a bearer token.

Dynamic client registration (RFC 7591, /oauth/register) is intentionally open -
it grants nothing by itself. The admin approval endpoints below (/api/oauth-clients,
gated like any other admin route) are the real trust boundary: /oauth/authorize
refuses to render consent for a client that isn't explicitly approved, which is
what stops a phishing client calling itself "Claude" from getting a logged-in
operator to approve it just by registering a shell with a plausible name."""

import secrets
import time
from collections import defaultdict
from urllib.parse import urlencode, urlparse

from flask import Blueprint, current_app, jsonify, redirect, request, session
from markupsafe import escape

from ..accounts import mcp_keys
from ..accounts import oauth_server
from ..accounts import users as accounts_users
from ..accounts.permissions import require_permission

bp = Blueprint("oauth", __name__)

REGISTER_RATE_LIMIT = 10
REGISTER_RATE_WINDOW = 3600  # seconds, hygiene against junk rows - not a security boundary
_register_hits = defaultdict(list)


def _oauth_error(error, description=None, status=400):
    body = {"error": error}
    if description:
        body["error_description"] = description
    return jsonify(body), status


def _public_base_url():
    configured = current_app.config.get("REVENUE_CONSOLE_PUBLIC_URL")
    return (configured or request.url_root).rstrip("/")


def _current_user():
    user_id = session.get("user_id")
    if user_id is None:
        return None
    user = accounts_users.get_user(user_id)
    return user if user and user["isActive"] else None


def _registration_rate_limited(ip):
    now = time.time()
    hits = [t for t in _register_hits[ip] if now - t < REGISTER_RATE_WINDOW]
    hits.append(now)
    _register_hits[ip] = hits
    return len(hits) > REGISTER_RATE_LIMIT


# ---- HTML (the only HTML this backend renders - everything else is JSON) --------

def _page(title, body):
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{escape(title)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body {{ font-family: system-ui, sans-serif; max-width: 420px; margin: 10vh auto; padding: 0 16px; color: #1f2937; }}
h1 {{ font-size: 1.1rem; }}
label {{ display: block; margin: 12px 0 4px; font-size: 0.85rem; font-weight: 600; }}
input[type=text], input[type=password] {{ width: 100%; padding: 8px; border: 1px solid #cbd5e1; border-radius: 6px; box-sizing: border-box; }}
button {{ margin-top: 16px; padding: 8px 16px; border-radius: 6px; border: none; font-weight: 600; cursor: pointer; }}
.primary {{ background: #0f172a; color: white; }}
.secondary {{ background: #e2e8f0; color: #0f172a; margin-left: 8px; }}
.error {{ color: #b91c1c; font-size: 0.85rem; margin-top: 8px; }}
</style></head><body>{body}</body></html>"""


def _login_form(flow_id, error=None):
    err_html = f'<p class="error">{escape(error)}</p>' if error else ""
    return _page("Sign in - Revenue Console", f"""
<h1>Sign in to Revenue Console</h1>
<form method="post">
  <input type="hidden" name="action" value="login">
  <input type="hidden" name="flow_id" value="{escape(flow_id)}">
  <label for="username">Username</label>
  <input type="text" id="username" name="username" autocomplete="username" required autofocus>
  <label for="password">Password</label>
  <input type="password" id="password" name="password" autocomplete="current-password" required>
  {err_html}
  <button type="submit" class="primary">Sign in</button>
</form>
""")


def _consent_form(flow_id, client_name, redirect_host, display_name):
    return _page("Allow access? - Revenue Console", f"""
<h1>Allow access?</h1>
<p><strong>{escape(client_name)}</strong> (redirecting to <code>{escape(redirect_host)}</code>)
wants to read Revenue Console data as <strong>{escape(display_name)}</strong>.</p>
<form method="post">
  <input type="hidden" name="action" value="consent">
  <input type="hidden" name="flow_id" value="{escape(flow_id)}">
  <button type="submit" name="decision" value="allow" class="primary">Allow</button>
  <button type="submit" name="decision" value="deny" class="secondary">Deny</button>
</form>
""")


def _error_page(message, status=400):
    return _page("Can't continue", f"<h1>Can't continue</h1><p>{escape(message)}</p>"), status


# ---- AS metadata + dynamic client registration -----------------------------------

@bp.route("/.well-known/oauth-authorization-server", methods=["GET"])
def as_metadata():
    base = _public_base_url()
    return jsonify({
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
    })


@bp.route("/oauth/register", methods=["POST"])
def register():
    if _registration_rate_limited(request.remote_addr or "unknown"):
        return _oauth_error("too_many_requests", "Try again later", 429)
    data = request.get_json(silent=True) or {}
    try:
        client_id = oauth_server.register_client(data.get("client_name", ""), data.get("redirect_uris"))
    except oauth_server.ValidationError as exc:
        return _oauth_error("invalid_client_metadata", str(exc))
    client = oauth_server.get_client(client_id)
    return jsonify({
        "client_id": client_id,
        "client_name": client["clientName"],
        "redirect_uris": client["redirectUris"],
        "token_endpoint_auth_method": "none",
    }), 201


# ---- authorize: login then consent, both guarded by the same flow_id ------------

@bp.route("/oauth/authorize", methods=["GET", "POST"])
def authorize():
    if request.method == "GET":
        return _authorize_start()
    action = request.form.get("action")
    if action == "login":
        return _authorize_login()
    if action == "consent":
        return _authorize_consent()
    return _error_page("Invalid request")


def _authorize_start():
    if request.args.get("response_type") != "code":
        return _error_page("Only response_type=code is supported")
    client_id = request.args.get("client_id", "")
    redirect_uri = request.args.get("redirect_uri", "")
    code_challenge = request.args.get("code_challenge", "")
    code_challenge_method = request.args.get("code_challenge_method")
    state = request.args.get("state", "")

    client = oauth_server.get_client(client_id)
    if not client:
        return _error_page("Unknown client")
    if redirect_uri not in client["redirectUris"]:
        return _error_page("redirect_uri does not match this client's registration")
    if client["status"] != "approved":
        return _error_page(
            "This client hasn't been approved by an administrator yet. "
            "Ask an admin to approve it on the MCP Access page.")
    if not code_challenge or code_challenge_method != "S256":
        return _error_page("code_challenge_method=S256 is required")

    flow_id = secrets.token_urlsafe(16)
    session["oauth_flow"] = {
        "id": flow_id, "client_id": client_id, "client_name": client["clientName"],
        "redirect_uri": redirect_uri, "state": state, "code_challenge": code_challenge,
    }

    user = _current_user()
    if user:
        return _consent_form(flow_id, client["clientName"], urlparse(redirect_uri).netloc, user["displayName"])
    return _login_form(flow_id)


def _pending_flow():
    pending = session.get("oauth_flow")
    if not pending or pending.get("id") != request.form.get("flow_id", ""):
        return None
    return pending


def _authorize_login():
    pending = _pending_flow()
    if not pending:
        return _error_page("This sign-in link expired. Close this tab and try connecting again.")
    user = accounts_users.verify_login(request.form.get("username", ""), request.form.get("password", ""))
    if not user:
        return _login_form(pending["id"], error="Invalid username or password")

    # Mirrors /api/auth/login's own session.clear()/set sequence exactly (this
    # incidentally also logs the operator into the SPA) - the pending flow has
    # to survive that clear, so it's captured first and restored after.
    session.clear()
    session.permanent = True
    session["user_id"] = user["id"]
    session["oauth_flow"] = pending

    client = oauth_server.get_client(pending["client_id"])
    if not client or client["status"] != "approved":
        return _error_page("This client is no longer approved.")
    return _consent_form(pending["id"], client["clientName"], urlparse(pending["redirect_uri"]).netloc, user["displayName"])


def _authorize_consent():
    pending = _pending_flow()
    if not pending:
        return _error_page("This sign-in link expired. Close this tab and try connecting again.")
    user = _current_user()
    if not user:
        return _login_form(pending["id"])

    session.pop("oauth_flow", None)
    client = oauth_server.get_client(pending["client_id"])
    if not client or client["status"] != "approved":
        return _error_page("This client is no longer approved.")

    redirect_uri = pending["redirect_uri"]
    state = pending.get("state", "")
    if request.form.get("decision") == "allow":
        code = oauth_server.create_code(pending["client_id"], user["id"], redirect_uri, pending["code_challenge"])
        target = f"{redirect_uri}?{urlencode({'code': code, 'state': state})}"
    else:
        target = f"{redirect_uri}?{urlencode({'error': 'access_denied', 'state': state})}"
    return redirect(target, code=302)


# ---- token: the OAuth access_token IS an mcp_keys row ---------------------------

@bp.route("/oauth/token", methods=["POST"])
def token():
    data = request.form if request.form else (request.get_json(silent=True) or {})
    if data.get("grant_type") != "authorization_code":
        return _oauth_error("unsupported_grant_type")

    client_id = data.get("client_id", "")
    client = oauth_server.get_client(client_id)
    if not client or client["status"] != "approved":
        return _oauth_error("invalid_client")

    user_id = oauth_server.consume_code(
        data.get("code", ""), client_id, data.get("redirect_uri", ""), data.get("code_verifier", ""))
    if user_id is None:
        return _oauth_error("invalid_grant")

    _record, access_token = mcp_keys.create_oauth_key(user_id, client_id, client["clientName"])
    return jsonify({"access_token": access_token, "token_type": "bearer"})


# ---- admin approval: the actual trust boundary ----------------------------------

@bp.route("/api/oauth-clients", methods=["GET"])
@require_permission("manage_users")
def list_oauth_clients():
    return jsonify({"status": "success", "clients": oauth_server.list_clients()})


@bp.route("/api/oauth-clients/<client_id>/approve", methods=["POST"])
@require_permission("manage_users")
def approve_oauth_client(client_id):
    if not oauth_server.approve_client(client_id):
        return jsonify({"status": "error", "message": "Client not found"}), 404
    return jsonify({"status": "success"})


@bp.route("/api/oauth-clients/<client_id>/reject", methods=["POST"])
@require_permission("manage_users")
def reject_oauth_client(client_id):
    if not oauth_server.reject_client(client_id):
        return jsonify({"status": "error", "message": "Client not found"}), 404
    return jsonify({"status": "success"})
