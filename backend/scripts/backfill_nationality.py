#!/usr/bin/env python3
"""One-time backfill: nationality for reservations that already checked in
before nationality capture existed (added 2026-11-05).

Nationality is unknown pre-check-in, so booking_events._connect() deliberately
excludes it from the company/group backfill there - forcing today's value
into a pre-check-in snapshot would misrepresent that past point in time. For
an already-completed stay that concern doesn't apply: nationality was fixed
at check-in, we just never recorded it. This resyncs every historical
ARRIVAL_DATE window through the normal fetch_window()/upsert() path, so each
reservation picks up nationality via the same version-diffing upsert() always
uses - it only appends a new terminal version when the payload actually
changed, so pre-check-in history is untouched.

Safe to interrupt and rerun: already-processed windows are a fast no-op.

Usage: python backend/scripts/backfill_nationality.py [--dry-run]
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(BACKEND_DIR / ".env")

from app.integrations.pms.api_client import PMSApiClient  # noqa: E402
from app.revenue import booking_events as be  # noqa: E402


def main():
    dry_run = "--dry-run" in sys.argv

    with be._db_lock, be._db() as conn:
        row = conn.execute("SELECT MIN(arrival_date) d FROM bookings").fetchone()
    if not row or not row["d"]:
        print("No bookings in the cache yet - run a normal backfill sync first.")
        sys.exit(1)

    start, end = be.date.fromisoformat(row["d"]), be._today()
    windows = be._windows(start, end)
    print(f"Resyncing {len(windows)} ARRIVAL_DATE window(s) from {start} to {end} "
          f"({'dry run, nothing written' if dry_run else 'live'})")

    client = PMSApiClient().login()
    total, failed = 0, []
    for i, (w_start, w_end) in enumerate(windows, 1):
        try:
            rows = be.fetch_window(client, "ARRIVAL_DATE", w_start, w_end)
            if dry_run:
                masters = be.master_rows(rows)
                with_nat = sum(1 for r in masters if r.get("NationalityDescription"))
                print(f"  [{i}/{len(windows)}] {w_start} -> {w_end}: "
                      f"{len(masters)} reservations, {with_nat} with nationality")
            else:
                n = be.upsert(rows)
                total += n
                print(f"  [{i}/{len(windows)}] {w_start} -> {w_end}: "
                      f"upserted {n} reservations (total {total})")
        except Exception as exc:
            print(f"  [{i}/{len(windows)}] {w_start} -> {w_end}: FAILED - {exc}")
            failed.append((w_start, w_end))

    if failed:
        print(f"\n{len(failed)} window(s) failed - rerun this script to retry them "
              "(already-synced windows are a fast no-op):")
        for w_start, w_end in failed:
            print(f"  {w_start} -> {w_end}")
        sys.exit(1)

    print("\nDry run complete - no data written." if dry_run else f"\nDone. {total} reservations upserted.")


if __name__ == "__main__":
    main()
