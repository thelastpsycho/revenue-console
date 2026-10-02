"""Overbooked dates (Occupancy > 100%) must not crash demand-level binning."""
import sqlite3

import pandas as pd

from app.revenue import yield_engine as engine


def _write_combined_inventory(path, rows):
    conn = sqlite3.connect(path)
    pd.DataFrame(rows).to_sql('combined_inventory', conn, index=False)
    conn.close()


def test_overbooked_occupancy_clamps_to_the_top_demand_bin(tmp_path):
    db_path = str(tmp_path / "combined_inventory.db")
    _write_combined_inventory(db_path, [
        {"Date": "2026-10-01", "Deluxe Room": -2, "Premiere Room": -3, "Occupancy": 100.62},
    ])
    data = engine.load_and_clean_data(
        db_path=db_path, required_room_types=['Deluxe Room', 'Premiere Room'],
    )
    assert data is not None
    row = data.iloc[0]
    assert row['DemandLevel'] == 'High'
    # The real Occupancy value is kept as-is (only binning is clamped).
    assert row['Occupancy'] == 100.62


def test_normal_occupancy_still_bins_correctly(tmp_path):
    db_path = str(tmp_path / "combined_inventory.db")
    _write_combined_inventory(db_path, [
        {"Date": "2026-10-01", "Deluxe Room": 50, "Premiere Room": 80, "Occupancy": 60},
        {"Date": "2026-10-02", "Deluxe Room": 50, "Premiere Room": 80, "Occupancy": 75},
        {"Date": "2026-10-03", "Deluxe Room": 50, "Premiere Room": 80, "Occupancy": 90},
    ])
    data = engine.load_and_clean_data(
        db_path=db_path, required_room_types=['Deluxe Room', 'Premiere Room'],
    )
    assert list(data['DemandLevel']) == ['Low', 'Medium', 'High']
