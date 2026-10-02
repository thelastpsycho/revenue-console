import pandas as pd
from tabulate import tabulate
from datetime import datetime
import os
import sqlite3
from ..infrastructure.paths import get_data_dir
from .upgrade_reserves import load_policy, prepare_capacity, reserve_offer, room_count

# Demand level configuration
DEMAND_BINS = [0, 70, 85, 100]  # Bins for Low, Medium, High demand
DEMAND_LABELS = ['Low', 'Medium', 'High']

# Threshold configuration for inventory levels
VERY_LOW_THRESHOLD_PCT = 0.05  # 5% of capacity
LOW_THRESHOLD_PCT = 0.2       # 20% of capacity

# Room capacity configuration
ROOM_CAPS = {
    'Deluxe Room': 160,
    'Premiere Room': 260,
    'Deluxe Pool Access': 22,
    'Premiere Room Lagoon Access': 26,
    'Premiere Suite Room': 9,
    'Deluxe Suite Room': 5,
    'Family Premiere Room': 4,
    'Beach Front Private Suite Room': 8,
    'The Anvaya Suite Whirpool': 4,
    'The Anvaya Suite No Pool': 4,
    'The Anvaya Suite With Pool': 2,
    'The Anvaya Residence': 1,
    'The Anvaya Villa': 1,
}

# Room types that get online inventory only (no BAR yielding).
# Availability is governed by shared capacity, not a hotel occupancy cutoff.
SIMPLE_ROOM_TYPES = [k for k in ROOM_CAPS if k not in ('Deluxe Room', 'Premiere Room')]

# Override configuration
DELUXE_OVERRIDE_OCCUPANCY = 70  # Override threshold for occupancy
DELUXE_OVERRIDE_PREMIERE = 31   # Override threshold for Premiere inventory
DELUXE_OVERRIDE_AMOUNT = 2      # Amount of Deluxe rooms to open in override

# Get the absolute path to the data directory within the scraper folder
DATA_DIR = get_data_dir()

def get_online_allotment(remaining, room_cap):
    """Tiered bucket allotment: how many rooms to open online given how many remain."""
    if remaining <= 0:
        return 0
    elif 1 <= remaining <= 5:
        return min(2, remaining, room_cap)
    elif 6 <= remaining <= 10:
        return min(5, remaining, room_cap)
    elif 11 <= remaining <= 50:
        return min(10, remaining, room_cap)
    else:  # remaining > 50
        return min(30, remaining, room_cap)

def allot_minus_one(remaining):
    return max(0, remaining - 1)

def allot_minus_one_except_one(remaining):
    if remaining <= 0:
        return 0
    if remaining == 1:
        return 1
    return remaining - 1

def allot_as_remaining(remaining):
    return max(0, remaining)

def allot_deluxe_suite(remaining, premiere_suite_remaining):
    if remaining >= 5:
        return 4
    elif remaining == 4:
        return 3
    elif remaining in (2, 3):
        return 2
    elif remaining == 1:
        return 1
    else:  # remaining <= 0
        return 1 if premiere_suite_remaining > 3 else 0

def should_override_deluxe(occupancy, premiere_inventory, deluxe_inventory,
                           occupancy_threshold=DELUXE_OVERRIDE_OCCUPANCY,
                           premiere_threshold=DELUXE_OVERRIDE_PREMIERE):
    """
    Determine if Deluxe inventory should be overridden based on conditions:
    1. Deluxe inventory is less than 1
    2. AND combined Deluxe+Premiere inventory is still > 0 (a Deluxe oversell can
        be upgraded into Premiere, but only while the two categories together
        still have rooms to sell — if the sum is <= 0 there is nothing left)
    3. AND (Occupancy is lower than occupancy_threshold
        OR Premiere inventory is higher than premiere_threshold)
    """
    return (deluxe_inventory < 1 and
            deluxe_inventory + premiere_inventory > 0 and
            (occupancy < occupancy_threshold or premiere_inventory > premiere_threshold))

# Load and clean the dataset
def load_and_clean_data(db_path=None, demand_bins=None, demand_labels=None, required_room_types=None):
    # Use default values if not provided
    demand_bins = demand_bins or DEMAND_BINS
    demand_labels = demand_labels or DEMAND_LABELS
    
    # Use the correct absolute path for the database
    if db_path is None:
        db_path = os.path.join(DATA_DIR, 'combined_inventory.db')
    
    print(f"Attempting to load data from: {db_path}")
    
    try:
        # Connect to SQLite database
        conn = sqlite3.connect(db_path)
        print("Successfully connected to database")
        
        # Read data from the combined_inventory table
        data = pd.read_sql_query("SELECT * FROM combined_inventory", conn)
        print(f"Successfully read {len(data)} rows from database")
        
        # Close the connection
        conn.close()
        
        # Print column names for debugging
        print("Available columns:", data.columns.tolist())
        
    except sqlite3.OperationalError as e:
        print(f"Database error: {e}")
        if "no such table" in str(e):
            print("Error: combined_inventory table does not exist. Please run combine inventory first.")
        return None
    except Exception as e:
        print(f"Error reading from database: {e}")
        return None
    
    # Map the actual column names to our expected names
    column_mapping = {
        'Deluxe Room': 'Deluxe Room',
        'Premiere Room': 'Premiere Room'
    }
    
    # Rename columns if they exist
    for old_name, new_name in column_mapping.items():
        if old_name in data.columns:
            data = data.rename(columns={old_name: new_name})
    
    all_inventory_columns = ['Deluxe Room', 'Premiere Room'] + SIMPLE_ROOM_TYPES
    required_room_types = required_room_types or all_inventory_columns
    missing_columns = [col for col in required_room_types if col not in data.columns]
    if missing_columns:
        print(f"Error: Missing required columns: {missing_columns}")
        print("Available columns:", data.columns.tolist())
        return None

    # Keep a stable schema for downstream diagnostics, while allowing a
    # Deluxe/Premiere-only calculation to proceed when an unrelated category
    # is absent from a partial snapshot.
    for col in all_inventory_columns:
        if col not in data.columns:
            data[col] = 0
    data = data[['Date', 'Deluxe Room', 'Premiere Room', 'Occupancy'] + SIMPLE_ROOM_TYPES]

    inventory_columns = all_inventory_columns
    required_columns = ['Occupancy'] + required_room_types
    if data[required_columns].isnull().any().any():
        raise ValueError('Incomplete inventory snapshot for the selected allocation scope: refresh PMS and CM before calculating allocation')
    # Nulls outside the requested scope are irrelevant to this run. Keep the
    # output schema usable, but do not let them abort Deluxe/Premiere allocation.
    outside_scope = [col for col in inventory_columns if col not in required_room_types]
    for col in outside_scope:
        data[col] = pd.to_numeric(data[col], errors='coerce').fillna(0)
    
    try:
        data['Date'] = pd.to_datetime(data['Date'])
    except Exception as e:
        print(f"Error: Invalid date format. {e}")
        return None
    
    def assign_season(date):
        year = date.year
        date_no_year = date.replace(year=2025)
        if (datetime(2025, 1, 1) <= date_no_year <= datetime(2025, 1, 3) or
            datetime(2025, 12, 27) <= date_no_year <= datetime(2025, 12, 31)):
            return 'Peak'
        elif (datetime(2025, 1, 4) <= date_no_year <= datetime(2025, 5, 31) or
              datetime(2025, 6, 1) <= date_no_year <= datetime(2025, 6, 30) or
              datetime(2025, 9, 1) <= date_no_year <= datetime(2025, 9, 30) or
              datetime(2025, 10, 1) <= date_no_year <= datetime(2025, 12, 22)):
            return 'Normal'
        elif (datetime(2025, 7, 1) <= date_no_year <= datetime(2025, 8, 31) or
              datetime(2025, 12, 23) <= date_no_year <= datetime(2025, 12, 26)):
            return 'High'
        else:
            print(f"Warning: Unassigned season for {date}. Defaulting to Normal.")
            return 'Normal'
    
    data['Season'] = data['Date'].apply(assign_season)
    
    try:
        # Overbooked dates (more rooms sold than capacity) can push Occupancy
        # past 100% - pd.cut returns NaN past the last bin edge, which would
        # otherwise crash the whole yield step on a single bad date. Clamp
        # only for demand-level binning; the real (unclamped) Occupancy value
        # is kept as-is for display and for the Deluxe override check below.
        data['DemandLevel'] = pd.cut(
            data['Occupancy'].clip(upper=demand_bins[-1]),
            bins=demand_bins,
            labels=demand_labels,
            include_lowest=True
        )
    except Exception as e:
        print(f"Error: Invalid Occupancy values. {e}")
        return None
    
    data['DayOfWeek'] = data['Date'].dt.day_name()
    
    if (data[inventory_columns] < 0).any().any():
        print("Warning: Negative inventory values detected.")
    
    return data

# Apply yield matrix with limited online allotment and BAR based on remaining inventory
def apply_yield_matrix(data, very_low_threshold_pct=None, low_threshold_pct=None, room_caps=None,
                       include_simple_rooms=True,
                       deluxe_override_occupancy=None, deluxe_override_premiere=None,
                       deluxe_override_amount=None, bar_level_shift=0, allocation_policy=None):
    # Use default values if not provided
    very_low_threshold_pct = very_low_threshold_pct or VERY_LOW_THRESHOLD_PCT
    low_threshold_pct = low_threshold_pct or LOW_THRESHOLD_PCT
    room_caps = {**ROOM_CAPS, **(room_caps or {})}
    policy = load_policy(ROOM_CAPS, allocation_policy)
    allocation_scope = ['Deluxe Room', 'Premiere Room']
    if include_simple_rooms:
        allocation_scope += SIMPLE_ROOM_TYPES
    # Whole ranks to shift the base BAR matrix toward the more expensive tier
    # (negative shifts toward cheaper), applied before scarcity escalation.
    bar_level_shift = int(bar_level_shift) if bar_level_shift else 0

    # Deluxe override configuration (fall back to module defaults when not supplied)
    if deluxe_override_occupancy is None:
        deluxe_override_occupancy = DELUXE_OVERRIDE_OCCUPANCY
    if deluxe_override_premiere is None:
        deluxe_override_premiere = DELUXE_OVERRIDE_PREMIERE
    if deluxe_override_amount is None:
        deluxe_override_amount = DELUXE_OVERRIDE_AMOUNT

    # Defensive check for required columns
    required_columns = ['Deluxe Room', 'Premiere Room']
    for col in required_columns:
        if col not in data.columns:
            print(f"Error: Required column '{col}' not found! Available columns: {data.columns.tolist()}")
            raise Exception(f"Required column '{col}' not found! Available columns: {data.columns.tolist()}")

    yield_matrix = {
        'Deluxe Room': {
            'Normal': {
                'High': {'bar': 'BAR4'},
                'Medium': {'bar': 'BAR5'},
                'Low': {'bar': 'BAR7'}
            },
            'High': {
                'High': {'bar': 'BAR2'},
                'Medium': {'bar': 'BAR3'},
                'Low': {'bar': 'BAR5'}
            },
            'Peak': {
                'High': {'bar': 'BAR2'},
                'Medium': {'bar': 'BAR3'},
                'Low': {'bar': 'BAR4'}
            }
        },
        'Premiere Room': {
            'Normal': {
                'High': {'bar': 'BAR4'},
                'Medium': {'bar': 'BAR5'},
                'Low': {'bar': 'BAR7'}
            },
            'High': {
                'High': {'bar': 'BAR2'},
                'Medium': {'bar': 'BAR3'},
                'Low': {'bar': 'BAR5'}
            },
            'Peak': {
                'High': {'bar': 'BAR2'},
                'Medium': {'bar': 'BAR3'},
                'Low': {'bar': 'BAR4'}
            }
        }
    }
    
    valid_bar_rates = {'BAR2', 'BAR3', 'BAR4', 'BAR5', 'BAR6', 'BAR7'}
    bar_rate_order = {'BAR7': 6, 'BAR6': 5, 'BAR5': 4, 'BAR4': 3, 'BAR3': 2, 'BAR2': 1}  # Lower number = more expensive
    bar_rate_reverse = {1: 'BAR2', 2: 'BAR3', 3: 'BAR4', 4: 'BAR5', 5: 'BAR6', 6: 'BAR7'}

    def shift_bar_base(base_bar, season):
        """Shift the matrix base BAR by whole ranks toward the more expensive
        tier (lower rank number), before scarcity escalation runs. Clamped at
        the same seasonal BAR2 floor as adjust_bar_rate, and at BAR7 (rank 6)
        on the cheap end."""
        if not bar_level_shift:
            return base_bar
        rank = bar_rate_order.get(base_bar, 4)
        min_rank = 1 if season in ('Peak', 'High') else 2
        max_rank = 6
        new_rank = max(min_rank, min(max_rank, rank - bar_level_shift))
        return bar_rate_reverse.get(new_rank, base_bar)

    deluxe_override_amount = room_count(deluxe_override_amount, 'Deluxe override amount')
    data['Unresolved Upgrade Rooms'] = 0
    data['Allocation Status'] = 'Ready'
    for room in ROOM_CAPS:
        for suffix in ('Upgrade Reserve', 'Override Reserve', 'Operational Hold', 'Safe Inventory'):
            data[f'{room} {suffix}'] = 0

    data['Deluxe Online Inventory'] = 0
    data['Deluxe BAR Rate'] = ''
    data['Premiere Online Inventory'] = 0
    data['Premiere BAR Rate'] = ''
    if include_simple_rooms:
        for room_type in SIMPLE_ROOM_TYPES:
            data[f'{room_type} Online Inventory'] = 0

    for idx, row in data.iterrows():
        season = row['Season']
        demand = row['DemandLevel']
        if pd.isna(demand):
            raise ValueError(f"Invalid occupancy/demand for {row['Date']}")

        # Defensive check for required keys in the row
        if 'Premiere Room' not in row or 'Deluxe Room' not in row:
            print(f"Error: Row {idx} is missing 'Premiere Room' or 'Deluxe Room'. Row keys: {row.keys().tolist()}")
            continue

        premiere_remaining = row['Premiere Room']
        deluxe_remaining = row['Deluxe Room']

        # Function to adjust BAR rate based on remaining inventory
        def adjust_bar_rate(base_bar, remaining_inventory, room_type, demand, season):
            
            capacity = room_caps[room_type]
            very_low_threshold = capacity * very_low_threshold_pct
            low_threshold = capacity * low_threshold_pct
            
            base_rank = bar_rate_order.get(base_bar, 4)  # Default to BAR5 if invalid
            # BAR2 (rank 1) is reserved for Peak/High seasons; Normal season
            # scarcity escalation is capped at BAR3 (rank 2).
            min_rank = 1 if season in ('Peak', 'High') else 2
            if remaining_inventory <= very_low_threshold:
                new_rank = max(min_rank, base_rank - 2)  # Shift up 2 levels, seasonal ceiling
                print(f"{row['Date'].strftime('%Y-%m-%d')} {room_type}: Remaining {remaining_inventory} (Very Low) → {base_bar} to {bar_rate_reverse[new_rank]}")
            elif remaining_inventory <= low_threshold:
                new_rank = max(min_rank, base_rank - 1)  # Shift up 1 level, seasonal ceiling
                print(f"{row['Date'].strftime('%Y-%m-%d')} {room_type}: Remaining {remaining_inventory} (Low) → {base_bar} to {bar_rate_reverse[new_rank]}")
            else:
                new_rank = base_rank  # No change
                print(f"{row['Date'].strftime('%Y-%m-%d')} {room_type}: Remaining {remaining_inventory} (Moderate/High) → {base_bar}")
            return bar_rate_reverse.get(new_rank, 'BAR5')
        
        # Premiere Room
        room = 'Premiere Room'
        remaining = premiere_remaining
        base_bar = yield_matrix[room][season][demand]['bar']
        if base_bar not in valid_bar_rates:
            print(f"Warning: Invalid Premiere BAR Rate '{base_bar}' for {row['Date'].strftime('%Y-%m-%d')}. Using BAR5.")
            base_bar = 'BAR5'
        base_bar = shift_bar_base(base_bar, season)
        bar_rate = adjust_bar_rate(base_bar, remaining, room, demand, season)
        
        data.at[idx, 'Premiere BAR Rate'] = bar_rate
        
        # Deluxe Room
        room = 'Deluxe Room'
        remaining = deluxe_remaining

        base_bar = yield_matrix[room][season][demand]['bar']
        if base_bar not in valid_bar_rates:
            print(f"Warning: Invalid Deluxe BAR Rate '{base_bar}' for {row['Date'].strftime('%Y-%m-%d')}. Using BAR5.")
            base_bar = 'BAR5'
        base_bar = shift_bar_base(base_bar, season)
        bar_rate = adjust_bar_rate(base_bar, remaining, room, demand, season)
        
        data.at[idx, 'Deluxe BAR Rate'] = bar_rate

        # Rebuild capacity from the current snapshot. PMS assignments have
        # already restored the booked type and deducted the physical destination.
        remaining_by_room = {room: row[room] for room in allocation_scope}
        safe, reserved, protected, online_caps, unresolved = prepare_capacity(
            remaining_by_room, policy, row['Date'].strftime('%Y-%m-%d'), room_scope=allocation_scope)
        override_reserves = dict.fromkeys(ROOM_CAPS, 0)
        allocations = dict.fromkeys(ROOM_CAPS, 0)
        if not unresolved:
            # New borrowed sales consume the same capacity as direct sales.
            # Preserve Deluxe's existing override trigger, but reserve its backing
            # BEFORE calculating Premiere's direct release.
            if should_override_deluxe(row['Occupancy'], premiere_remaining, deluxe_remaining,
                                      deluxe_override_occupancy, deluxe_override_premiere):
                amount = min(deluxe_override_amount, online_caps.get('Deluxe Room', deluxe_override_amount))
                # Deluxe overrides retain their existing Premiere-only backing.
                # Higher rooms cover existing guests; this does not introduce
                # additional deliberate Premiere overselling.
                allocations['Deluxe Room'] = reserve_offer(
                    'Deluxe Room', amount, safe,
                    {'Deluxe Room': ['Premiere Room']} if 'Premiere Room' in policy['routes']['Deluxe Room'] else {},
                    override_reserves)
            else:
                allocations['Deluxe Room'] = get_online_allotment(safe['Deluxe Room'], room_caps['Deluxe Room'])

            if include_simple_rooms:
                if remaining_by_room['Deluxe Suite Room'] <= 0 and safe['Premiere Suite Room'] > 3:
                    allocations['Deluxe Suite Room'] = reserve_offer(
                        'Deluxe Suite Room', min(1, online_caps.get('Deluxe Suite Room', 1)),
                        safe, policy['routes'], override_reserves)
                for room_type in SIMPLE_ROOM_TYPES:
                    remaining = safe[room_type]
                    if room_type in ('Deluxe Pool Access', 'Premiere Room Lagoon Access', 'Premiere Suite Room'):
                        allocations[room_type] = get_online_allotment(remaining, room_caps[room_type])
                    elif room_type == 'Deluxe Suite Room':
                        if remaining_by_room[room_type] > 0:
                            allocations[room_type] = allot_deluxe_suite(remaining, 0)
                    elif room_type == 'Beach Front Private Suite Room':
                        allocations[room_type] = allot_minus_one_except_one(remaining)
                    elif room_type in ('Family Premiere Room', 'The Anvaya Suite Whirpool', 'The Anvaya Suite No Pool'):
                        allocations[room_type] = allot_minus_one(remaining)
                    else:
                        allocations[room_type] = allot_as_remaining(remaining)
            allocations['Premiere Room'] = get_online_allotment(safe['Premiere Room'], room_caps['Premiere Room'])
        else:
            data.at[idx, 'Allocation Status'] = 'Blocked: upgrade capacity or routes insufficient'
        data.at[idx, 'Unresolved Upgrade Rooms'] = unresolved
        for room_type in ROOM_CAPS:
            data.at[idx, f'{room_type} Upgrade Reserve'] = reserved.get(room_type, 0)
            data.at[idx, f'{room_type} Override Reserve'] = override_reserves.get(room_type, 0)
            data.at[idx, f'{room_type} Operational Hold'] = protected.get(room_type, 0)
            data.at[idx, f'{room_type} Safe Inventory'] = safe.get(room_type, 0)
            prefix = {'Deluxe Room': 'Deluxe', 'Premiere Room': 'Premiere'}.get(room_type, room_type)
            if room_type in ('Deluxe Room', 'Premiere Room') or include_simple_rooms:
                data.at[idx, f'{prefix} Online Inventory'] = min(
                    allocations[room_type], online_caps.get(room_type, allocations[room_type]))

    return data

def diagnostic_columns():
    return ['Allocation Status', 'Unresolved Upgrade Rooms'] + [
        f'{room} {suffix}' for room in ROOM_CAPS
        for suffix in ('Upgrade Reserve', 'Override Reserve', 'Operational Hold', 'Safe Inventory')]


def apply_custom_yield(config):
    """Run the custom yield calculation (from a
    /api/custom-yield-shaped config dict) and persist the result to
    inventory_allocation.db. Raises FileNotFoundError if combined_inventory.db
    is missing, or RuntimeError if the load/compute/write step fails, instead
    of returning None, so callers can catch and report a clear error."""
    combined_db_path = os.path.join(DATA_DIR, 'combined_inventory.db')
    if not os.path.exists(combined_db_path):
        raise FileNotFoundError("Combined inventory database not found. Please run combine inventory first.")

    include_simple_rooms = config.get('include_simple_rooms', False)
    if not isinstance(include_simple_rooms, bool):
        raise ValueError('include_simple_rooms must be a boolean')
    required_room_types = ['Deluxe Room', 'Premiere Room'] + (SIMPLE_ROOM_TYPES if include_simple_rooms else [])
    data = load_and_clean_data(
        demand_bins=config['demand_bins'],
        demand_labels=config['demand_labels'],
        required_room_types=required_room_types
    )
    if data is None:
        raise RuntimeError("Failed to load and clean data")

    bar_level_shift = int(config.get('bar_level_shift', 0) or 0)

    result = apply_yield_matrix(
        data,
        very_low_threshold_pct=config['very_low_threshold_pct'] / 100,
        low_threshold_pct=config['low_threshold_pct'] / 100,
        room_caps=config['room_caps'],
        include_simple_rooms=include_simple_rooms,
        deluxe_override_occupancy=config['deluxe_override_occupancy'],
        deluxe_override_premiere=config['deluxe_override_premiere'],
        deluxe_override_amount=config['deluxe_override_amount'],
        bar_level_shift=bar_level_shift
    )

    # Preserve existing base-column names, plus per-category diagnostics.
    result = result.rename(columns={
        'Deluxe Room': 'Deluxe Remaining Inventory',
        'Premiere Room': 'Premiere Remaining Inventory',
        **{room: f'{room} Remaining Inventory' for room in SIMPLE_ROOM_TYPES}
    })
    extra_columns = diagnostic_columns() + [f'{room} Remaining Inventory' for room in SIMPLE_ROOM_TYPES]
    if include_simple_rooms:
        extra_columns += [f'{room} Online Inventory' for room in SIMPLE_ROOM_TYPES]
    result = result[[
        'Date', 'DayOfWeek', 'Season', 'Occupancy', 'DemandLevel',
        'Deluxe Remaining Inventory', 'Deluxe Online Inventory', 'Deluxe BAR Rate',
        'Premiere Remaining Inventory', 'Premiere Online Inventory', 'Premiere BAR Rate'
    ] + extra_columns]
    result['Occupancy'] = result['Occupancy'].round(2)
    result['Date'] = pd.to_datetime(result['Date']).dt.strftime('%Y-%m-%d')

    db_path = os.path.join(DATA_DIR, 'inventory_allocation.db')
    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA foreign_keys = ON')
    dtype = {
        'Date': 'DATE',
        'DayOfWeek': 'TEXT',
        'Season': 'TEXT',
        'Occupancy': 'REAL',
        'DemandLevel': 'TEXT',
        'Deluxe Remaining Inventory': 'INTEGER',
        'Deluxe Online Inventory': 'INTEGER',
        'Deluxe BAR Rate': 'TEXT',
        'Premiere Remaining Inventory': 'INTEGER',
        'Premiere Online Inventory': 'INTEGER',
        'Premiere BAR Rate': 'TEXT'
    }
    dtype.update({col: ('TEXT' if col == 'Allocation Status' else 'INTEGER') for col in extra_columns})
    result.to_sql('daily_inventory_allocation', conn, if_exists='replace', index=False, dtype=dtype)
    count = conn.execute("SELECT COUNT(*) FROM daily_inventory_allocation").fetchone()[0]
    conn.close()
    if count == 0:
        raise RuntimeError("No data was written to the inventory allocation database")

    return result

# Main execution
def main():
    try:
        print("Starting yield calculation process...")
        data = load_and_clean_data(required_room_types=['Deluxe Room', 'Premiere Room'])
        if data is None:
            print("Error: Failed to load and clean data")
            return None
        
        print("Applying yield matrix...")
        data = apply_yield_matrix(data, include_simple_rooms=False)
        
        # Create a copy of the data with the correct column names
        output = data.copy()
        
        # Rename the columns to match the expected output format
        output = output.rename(columns={
            'Deluxe Room': 'Deluxe Remaining Inventory',
            'Premiere Room': 'Premiere Remaining Inventory',
            **{room_type: f'{room_type} Remaining Inventory' for room_type in SIMPLE_ROOM_TYPES}
        })

        # Select and order the columns for output
        simple_room_columns = []

        output = output[[
            'Date', 'DayOfWeek', 'Season', 'Occupancy', 'DemandLevel',
            'Deluxe Remaining Inventory', 'Deluxe Online Inventory', 'Deluxe BAR Rate',
            'Premiere Remaining Inventory', 'Premiere Online Inventory', 'Premiere BAR Rate'
        ] + simple_room_columns + diagnostic_columns()]
        
        # Format the date and occupancy
        output['Date'] = output['Date'].dt.strftime('%Y-%m-%d')
        output['Occupancy'] = output['Occupancy'].round(2)
        
        print("\n=== Day-by-Day Inventory Allocation ===")
        print(tabulate(output, headers='keys', tablefmt='grid', showindex=False))
        
        # Create data directory if it doesn't exist
        os.makedirs(DATA_DIR, exist_ok=True)
        print(f"Ensuring data directory exists: {DATA_DIR}")
        
        # Save to SQLite (single source of truth handed off to the allotment updaters)
        db_path = os.path.join(DATA_DIR, 'inventory_allocation.db')
        print(f"Attempting to save to database: {db_path}")
        
        # Connect to SQLite database
        conn = sqlite3.connect(db_path)
        print("Connected to SQLite database")
        
        # Enable date handling in SQLite
        conn.execute('PRAGMA foreign_keys = ON')
        
        # Define SQLite data types for each column
        dtype = {
            'Date': 'DATE',
            'DayOfWeek': 'TEXT',
            'Season': 'TEXT',
            'Occupancy': 'REAL',
            'DemandLevel': 'TEXT',
            'Deluxe Remaining Inventory': 'INTEGER',
            'Deluxe Online Inventory': 'INTEGER',
            'Deluxe BAR Rate': 'TEXT',
            'Premiere Remaining Inventory': 'INTEGER',
            'Premiere Online Inventory': 'INTEGER',
            'Premiere BAR Rate': 'TEXT',
            **{col: 'INTEGER' for col in simple_room_columns}
        }
        
        # Save to database
        dtype.update({col: ('TEXT' if col == 'Allocation Status' else 'INTEGER') for col in diagnostic_columns()})
        output.to_sql('daily_inventory_allocation', conn, if_exists='replace', index=False, dtype=dtype)
        
        # Verify the data was written
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM daily_inventory_allocation")
        count = cursor.fetchone()[0]
        conn.close()

        if count == 0:
            print("Warning: No data was written to the database")
            return None
            
        print(f"Successfully wrote {count} rows to database")
        return output
        
    except Exception as e:
        print(f"Error in main function: {str(e)}")
        if 'conn' in locals():
            try:
                conn.close()
                print("Database connection closed after error")
            except:
                pass
        raise

if __name__ == "__main__":
    main()
