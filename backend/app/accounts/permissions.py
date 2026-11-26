"""Fixed catalog of fine-grained feature permissions.

Each key gates one cluster of mutating routes (see routes/*.py for where
@require_permission is applied). Plain read-only dashboards are not gated -
any authenticated user can view them regardless of permissions.
"""

from functools import wraps

from flask import g, jsonify

PERMISSIONS = [
    {"key": "manage_users", "label": "Manage users", "group": "Administration",
     "description": "Create, edit, disable accounts and reset passwords."},
    {"key": "manage_oauth_clients", "label": "Manage OAuth clients", "group": "Administration",
     "description": "Approve or reject MCP clients requesting OAuth access."},
    {"key": "manage_mcp_keys", "label": "Manage MCP keys", "group": "Administration",
     "description": "View and revoke other users' personal API keys (everyone can already manage their own)."},
    {"key": "run_pms_scrape", "label": "Run PMS scrape", "group": "Inventory collection",
     "description": "Scrape room availability from the PMS."},
    {"key": "view_pms_scrape_logs", "label": "View PMS scrape logs", "group": "Inventory collection",
     "description": "Watch the live log output of a PMS scrape without being able to start one."},
    {"key": "run_dedge_scrape", "label": "Run D-EDGE/CM scrape", "group": "Inventory collection",
     "description": "Scrape room planning data from D-EDGE, including device-auth codes."},
    {"key": "view_dedge_scrape_logs", "label": "View D-EDGE/CM scrape logs", "group": "Inventory collection",
     "description": "Watch the live log output of a D-EDGE/CM scrape without being able to start one."},
    {"key": "run_yield", "label": "Run yield engine", "group": "Yield management",
     "description": "Combine inventory and run the yield engine."},
    {"key": "push_pms_allotment", "label": "Push allotment to PMS", "group": "Allotment",
     "description": "Push calculated room allotment changes into the PMS."},
    {"key": "push_dedge_bar", "label": "Push BAR to D-EDGE", "group": "BAR pricing",
     "description": "Push calculated BAR price levels into D-EDGE."},
    {"key": "manage_bar_holds", "label": "Manage BAR holds", "group": "BAR pricing",
     "description": "Add or remove dates a BAR update must leave alone."},
    {"key": "run_pipeline", "label": "Run automation pipeline", "group": "Pipeline",
     "description": "Start and stop the end-to-end automation pipeline."},
    {"key": "manage_pipeline_schedule", "label": "Manage pipeline schedule", "group": "Pipeline",
     "description": "Edit the Fast API Pipeline's automated schedule."},
    {"key": "manage_season_calendar", "label": "Manage season calendar", "group": "Settings",
     "description": "Edit the named date ranges that set the yield engine's season tier."},
    {"key": "manage_allotment_rules", "label": "Manage allotment rules", "group": "Settings",
     "description": "Edit per-room-type release rules and suite upgrade routing."},
    {"key": "manage_stop_sale", "label": "Manage stop sale", "group": "Settings",
     "description": "Edit stop-sale rules/recipients and send stop-sale emails."},
    {"key": "manage_rms_settings", "label": "Manage RMS settings", "group": "Settings",
     "description": "Edit revenue rules, thresholds and budgets."},
    {"key": "manage_rms_notes", "label": "Manage RMS notes", "group": "Settings",
     "description": "Edit RMS meeting notes."},
    {"key": "view_dashboard", "label": "View dashboard", "group": "Page access",
     "description": "See the Dashboard overview page."},
    {"key": "view_data", "label": "View data overview", "group": "Page access",
     "description": "See the combined PMS/channel-manager inventory tables."},
    {"key": "view_rms", "label": "View RMS", "group": "Page access",
     "description": "See RMS and its sub-pages: Online segment, Pickup by month, Company analytics, Nationality analytics."},
    {"key": "view_mcp_access", "label": "View MCP Access page", "group": "Page access",
     "description": "See the MCP Access page to create personal API keys."},
    {"key": "view_documentation", "label": "View documentation", "group": "Page access",
     "description": "See the Documentation page."},
    {"key": "view_administration", "label": "View administration", "group": "Page access",
     "description": "See the Administration overview page."},
]

PERMISSION_KEYS = {entry["key"] for entry in PERMISSIONS}


def require_permission(key):
    """Route decorator: 403 unless the current session's user has `key`."""
    if key not in PERMISSION_KEYS:
        raise ValueError(f"Unknown permission key: {key}")

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = getattr(g, "current_user", None)
            if not user or key not in user.get("permissions", ()):
                return jsonify({"status": "error", "message": "Forbidden"}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def require_any_permission(*keys):
    """Route decorator: 403 unless the current session's user has at least
    one of `keys` - for data an endpoint serves to more than one page/role
    (e.g. inventory-allocation, read by both the yield and data-overview pages)."""
    unknown = [key for key in keys if key not in PERMISSION_KEYS]
    if unknown:
        raise ValueError(f"Unknown permission key(s): {', '.join(unknown)}")

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = getattr(g, "current_user", None)
            if not user or not (set(keys) & set(user.get("permissions", ()))):
                return jsonify({"status": "error", "message": "Forbidden"}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator
