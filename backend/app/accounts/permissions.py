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
    {"key": "run_pms_scrape", "label": "Run PMS scrape", "group": "Inventory collection",
     "description": "Scrape room availability from the PMS."},
    {"key": "run_dedge_scrape", "label": "Run D-EDGE/CM scrape", "group": "Inventory collection",
     "description": "Scrape room planning data from D-EDGE, including device-auth codes."},
    {"key": "run_yield", "label": "Run yield engine", "group": "Yield management",
     "description": "Combine inventory and run the yield engine."},
    {"key": "push_pms_allotment", "label": "Push allotment to PMS", "group": "Allotment",
     "description": "Push calculated room allotment changes into the PMS."},
    {"key": "push_dedge_bar", "label": "Push BAR to D-EDGE", "group": "BAR pricing",
     "description": "Push calculated BAR price levels into D-EDGE."},
    {"key": "manage_bar_holds", "label": "Manage BAR holds", "group": "BAR pricing",
     "description": "Add or remove dates a BAR update must leave alone."},
    {"key": "run_pipeline", "label": "Run automation pipeline", "group": "Pipeline",
     "description": "Start, stop, and schedule the end-to-end automation pipeline."},
    {"key": "manage_season_calendar", "label": "Manage season calendar", "group": "Settings",
     "description": "Edit the named date ranges that set the yield engine's season tier."},
    {"key": "manage_allotment_rules", "label": "Manage allotment rules", "group": "Settings",
     "description": "Edit per-room-type release rules and suite upgrade routing."},
    {"key": "manage_stop_sale", "label": "Manage stop sale", "group": "Settings",
     "description": "Edit stop-sale rules/recipients and send stop-sale emails."},
    {"key": "manage_rms_settings", "label": "Manage RMS settings", "group": "Settings",
     "description": "Edit revenue rules, thresholds, budgets and meeting notes."},
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
