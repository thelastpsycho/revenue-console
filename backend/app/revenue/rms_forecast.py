"""Live PMS forecast for the RMS page - pure pass-through, nothing stored.

Endpoint behaviour confirmed by live probes (2026-10-11):
- ReportForecastOccupancy always returns 7 days whatever `Days` says, but
  honours any TrxDate, so longer horizons are fetched in 7-day chunks.
- ReportForecastOccupancyMarketSegment honours `Days` exactly (one row per
  date per market segment).
- ReportExpectedRoomOccupied is also a fixed 7 days, pivoted: one row per
  room type with "MM-DD" columns plus NoOfRooms (that type's room count).
  It builds a server-side temp table named by hotel + timestamp, so
  concurrent calls collide ("Invalid object name 'xtempRoomAvail_...'") -
  its chunks are fetched one after another.

Room revenue only - no F&B/outlet fields are returned.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from ..integrations.pms.api_client import PMSApiClient

CHUNK = 7
# The segment call is slow (~27 s for 30 days, ~44 s for 90), so it's split
# into chunks fetched in parallel too, keeping a 90-day load well under the
# ~100 s Cloudflare tunnel request timeout.
SEGMENT_CHUNK = 14
MAX_DAYS = 90
WORKERS = 8


def _starts(start, days, chunk=CHUNK):
    return [start + timedelta(days=i) for i in range(0, days, chunk)]


def _post(client, name, trx_date, days=CHUNK):
    return client._api_post(name, {"TrxDate": trx_date.isoformat(), "Days": days,
                                   "HotelId": client.hotel_id, "UserId": client.user_id})


def _hotel(rows):
    return [{
        "date": r["TrxDate"][:10],
        "roomsSold": r.get("RoomUsed"),
        "roomCount": r.get("RoomCount"),
        "occupancy": r.get("Occupancy"),
        "revenue": r.get("RoomRevenue"),
        "adr": r.get("AverageRoomRate"),
        "complimentary": r.get("Complimentary"),
        "houseUse": r.get("HouseUse"),
        "lastYear": r.get("LastYearTransient"),
    } for r in rows]


def _segments(rows):
    return [{
        "date": r["TrxDate"][:10],
        "marketId": r.get("MarketId"),
        "market": r.get("MarketDescription"),
        "rooms": r.get("OnhandReservation"),
        "complimentary": r.get("OnhandCompliment"),
        "houseUse": r.get("OnhandHouseUse"),
        "revenue": r.get("OnhandRevenue"),
    } for r in rows]


def _room_types(rows):
    """Unpivots the "MM-DD" columns back to full dates using each row's
    StartDate (so a chunk spanning New Year resolves correctly)."""
    out = []
    for r in rows:
        start = date.fromisoformat(r["StartDate"][:10])
        for i in range(CHUNK):
            d = start + timedelta(days=i)
            key = f"{d:%m-%d}"
            if key in r:
                out.append({"date": d.isoformat(), "typeId": r["TypeId"],
                            "rooms": r[key], "roomCount": r.get("NoOfRooms")})
    return out


def fetch_forecast(start, days, client_factory=PMSApiClient):
    """Hotel-wide, market-segment and room-type forecast for `days` days from
    `start` (date). Rows outside the window (chunk overhang) are dropped."""
    days = max(1, min(int(days), MAX_DAYS))
    end = start + timedelta(days=days - 1)
    client = client_factory().login()
    starts = _starts(start, days)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        room_job = pool.submit(lambda: [r for s in starts for r in _post(client, "ReportExpectedRoomOccupied", s)])
        segment_jobs = [pool.submit(_post, client, "ReportForecastOccupancyMarketSegment", s,
                                    min(SEGMENT_CHUNK, (end - s).days + 1))
                        for s in _starts(start, days, SEGMENT_CHUNK)]
        hotel_jobs = [pool.submit(_post, client, "ReportForecastOccupancy", s) for s in starts]
        hotel = _hotel([r for j in hotel_jobs for r in j.result()])
        rooms = _room_types(room_job.result())
        segments = _segments([r for j in segment_jobs for r in j.result()])

    def within(rows):
        return sorted((r for r in rows if start.isoformat() <= r["date"] <= end.isoformat()),
                      key=lambda r: r["date"])

    return {"start": start.isoformat(), "end": end.isoformat(),
            "hotel": within(hotel), "segments": within(segments), "roomTypes": within(rooms)}
