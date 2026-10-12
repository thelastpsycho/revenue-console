"""Local operator settings and meeting notes; never writes to the PMS."""
import copy
import json
import math
from datetime import date

DEFAULT_SETTINGS = {
    "thresholds": {"occupancy": 90, "weakPickup": 5, "behindRooms": 10},
    "revenueRules": [{"rateType": "*", "from": "2000-01-01", "to": "2099-12-31",
                      "breakfast": 350000, "taxService": 0.21}],
    # Operator-entered targets: the discovered PMS budget endpoint has unverified units.
    "budgets": [],
}


def _number(value, name, low=0, high=1e15):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be a finite number from {low} to {high}")
    return value


def validate_settings(data):
    if not isinstance(data, dict):
        raise ValueError("Settings must be an object")
    thresholds = data.get("thresholds", {})
    if not isinstance(thresholds, dict):
        raise ValueError("thresholds must be an object")
    out = {"thresholds": {
        "occupancy": _number(thresholds.get("occupancy"), "occupancy", 0, 100),
        "weakPickup": _number(thresholds.get("weakPickup"), "weakPickup", 0, 100000),
        "behindRooms": _number(thresholds.get("behindRooms"), "behindRooms", 0, 100000),
    }}
    rules = data.get("revenueRules", [])
    budgets = data.get("budgets", [])
    if not isinstance(rules, list) or not 1 <= len(rules) <= 100 or not isinstance(budgets, list) or len(budgets) > 120:
        raise ValueError("Use 1–100 revenue rules and at most 120 monthly budgets")
    out["revenueRules"] = []
    for r in rules:
        if not isinstance(r, dict) or not isinstance(r.get("rateType"), str) or not 1 <= len(r["rateType"]) <= 40:
            raise ValueError("Each rule needs a rateType (or *)")
        first, last = date.fromisoformat(r.get("from", "")), date.fromisoformat(r.get("to", ""))
        if last < first:
            raise ValueError("Revenue rule end must not precede start")
        rate_id = r.get("rateId", "")
        if not isinstance(rate_id, str) or len(rate_id) > 80:
            raise ValueError("rateId must be text, at most 80 characters")
        for old in out["revenueRules"]:
            if old["rateType"] == r["rateType"] and old.get("rateId", "") == rate_id and old["from"] <= last.isoformat() and old["to"] >= first.isoformat():
                raise ValueError("Rules for the same rate type must not overlap")
        out["revenueRules"].append({"rateType": r["rateType"], "rateId": rate_id, "from": first.isoformat(), "to": last.isoformat(),
                                    "breakfast": _number(r.get("breakfast"), "breakfast"),
                                    "taxService": _number(r.get("taxService"), "taxService", 0, 1)})
    # A baseline prevents a valid settings save from breaking all gross/pace reports.
    baseline = sorted((r for r in out["revenueRules"] if r["rateType"] == "*" and not r["rateId"]), key=lambda r: r["from"])
    covered_until = date(1999, 12, 31)
    from datetime import timedelta
    for r in baseline:
        if date.fromisoformat(r["from"]) > covered_until + timedelta(days=1):
            break
        covered_until = max(covered_until, date.fromisoformat(r["to"]))
    if covered_until < date(2099, 12, 31):
        raise ValueError("Keep wildcard (*) baseline rules covering 2000–2099 without gaps")
    out["budgets"] = []
    months = set()
    for b in budgets:
        if not isinstance(b, dict) or not isinstance(b.get("month"), str) or len(b["month"]) != 7:
            raise ValueError("Budget month must be YYYY-MM")
        date.fromisoformat(b["month"] + "-01")
        if b["month"] in months or b.get("basis") not in ("gross", "net"):
            raise ValueError("Use one budget per month and basis gross or net")
        months.add(b["month"])
        out["budgets"].append({"month": b["month"], "basis": b["basis"],
                               "revenue": _number(b.get("revenue"), "budget revenue")})
    return out


def get_settings():
    from . import booking_events as be
    with be._db_lock, be._db() as conn:
        value = be._get_meta(conn, "rmsSettings")
    return json.loads(value) if value else copy.deepcopy(DEFAULT_SETTINGS)


def save_settings(data):
    from . import booking_events as be
    value = validate_settings(data)
    with be._db_lock, be._db() as conn:
        be._set_meta(conn, "rmsSettings", json.dumps(value))
    return value


def net_rate(rate, rate_type, day, rules, rate_id=None):
    matches = [r for r in rules if r["from"] <= day <= r["to"] and r["rateType"] in ("*", rate_type)
               and (not r.get("rateId") or r["rateId"] == rate_id)]
    matches.sort(key=lambda r: (bool(r.get("rateId")), r["rateType"] != "*"))
    if not matches:
        # Missing rules are a configuration error, not permission to invent a deduction.
        raise ValueError(f"No revenue rule covers {day} / {rate_type}")
    rule = matches[-1]
    return max(rate - rule["breakfast"], 0) / (1 + rule["taxService"])


def notes(start, end):
    from . import booking_events as be
    with be._db_lock, be._db() as conn:
        return {r["key"][8:]: json.loads(r["value"]) for r in conn.execute(
            "SELECT key, value FROM meta WHERE key BETWEEN ? AND ?", ("rmsNote:" + start, "rmsNote:" + end))}


def save_note(day, text):
    from . import booking_events as be
    day = date.fromisoformat(day).isoformat()
    if not isinstance(text, str) or len(text) > 2000:
        raise ValueError("Note must be text, at most 2,000 characters")
    value = {"text": text.strip(), "updatedAt": be._now()}
    with be._db_lock, be._db() as conn:
        be._set_meta(conn, "rmsNote:" + day, json.dumps(value))
    return value


def bar_context(start, end):
    """Confirmed local apply record, not a claim about the current live selling rate."""
    from pathlib import Path
    from . import booking_events as be
    path = Path(be.get_data_path("bar_last_applied.json"))
    if not path.exists():
        return {"byDate": {}, "updatedAt": None}
    try:
        data = json.loads(path.read_text())
        by_date = {}
        for room, days in data.items():
            for day, level in days.items():
                if start <= day <= end:
                    by_date.setdefault(day, {})[room] = level
        from datetime import datetime, timezone
        return {"byDate": by_date, "updatedAt": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()}
    except (ValueError, OSError, AttributeError, TypeError):
        return {"byDate": {}, "updatedAt": None, "error": "BAR apply record unavailable"}
