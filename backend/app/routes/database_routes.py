from flask import Blueprint, jsonify
import sqlite3
import os
import logging
from datetime import datetime, timezone
from ..infrastructure.paths import get_data_path
from ..accounts.permissions import require_any_permission

bp = Blueprint('database', __name__)

def get_db_path(db_name):
    return get_data_path(db_name)

def get_updated_at(db_name):
    """Last-modified time of a data file, as an ISO 8601 UTC string - shown in the
    UI as each tab's 'Updated on' so it's clear how fresh the data is."""
    db_path = get_db_path(db_name)
    if not os.path.exists(db_path):
        return None
    return datetime.fromtimestamp(os.path.getmtime(db_path), tz=timezone.utc).isoformat()

def get_db_connection(db_name):
    try:
        db_path = get_db_path(db_name)

        # Log the path for debugging
        logging.info(f"Attempting to connect to database at: {db_path}")

        if not os.path.exists(db_path):
            logging.error(f"Database file not found: {db_path}")
            raise FileNotFoundError(f"Database file not found: {db_path}")

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        logging.error(f"Error connecting to database {db_name}: {str(e)}")
        raise

@bp.route('/api/db/combined-inventory', methods=['GET', 'OPTIONS'])
@require_any_permission('view_data')
def get_combined_inventory():
    try:
        conn = get_db_connection('combined_inventory.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM combined_inventory')
        rows = cursor.fetchall()
        data = [dict(row) for row in rows]
        conn.close()
        return jsonify({"status": "success", "data": data, "updated_at": get_updated_at('combined_inventory.db')})
    except FileNotFoundError as e:
        logging.error(f"Database file not found: {str(e)}")
        return jsonify({"status": "error", "message": "Database file not found"}), 404
    except sqlite3.Error as e:
        logging.error(f"SQLite error: {str(e)}")
        return jsonify({"status": "error", "message": "Database error"}), 500
    except Exception as e:
        logging.error(f"Unexpected error in get_combined_inventory: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/api/db/inventory-allocation', methods=['GET', 'OPTIONS'])
@require_any_permission('view_data', 'run_yield')
def get_inventory_allocation():
    try:
        conn = get_db_connection('inventory_allocation.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM daily_inventory_allocation')
        rows = cursor.fetchall()
        data = [dict(row) for row in rows]
        conn.close()
        return jsonify({"status": "success", "data": data, "updated_at": get_updated_at('inventory_allocation.db')})
    except FileNotFoundError as e:
        logging.error(f"Database file not found: {str(e)}")
        return jsonify({"status": "error", "message": "Database file not found"}), 404
    except sqlite3.Error as e:
        logging.error(f"SQLite error: {str(e)}")
        return jsonify({"status": "error", "message": "Database error"}), 500
    except Exception as e:
        logging.error(f"Unexpected error in get_inventory_allocation: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/api/db/pms-inventory-processed', methods=['GET', 'OPTIONS'])
@require_any_permission('view_data')
def get_pms_inventory_processed():
    try:
        conn = get_db_connection('pms_inventory_processed.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM pms_inventory_processed')
        rows = cursor.fetchall()
        data = [dict(row) for row in rows]
        conn.close()
        return jsonify({"status": "success", "data": data, "updated_at": get_updated_at('pms_inventory_processed.db')})
    except FileNotFoundError as e:
        logging.error(f"Database file not found: {str(e)}")
        return jsonify({"status": "error", "message": "Database file not found"}), 404
    except sqlite3.Error as e:
        logging.error(f"SQLite error: {str(e)}")
        return jsonify({"status": "error", "message": "Database error"}), 500
    except Exception as e:
        logging.error(f"Unexpected error in get_pms_inventory_processed: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/api/db/bar-rates', methods=['GET', 'OPTIONS'])
@require_any_permission('push_dedge_bar')
def get_bar_rates():
    try:
        conn = get_db_connection('bar_rates.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM bar_rates')
        rows = cursor.fetchall()
        data = [dict(row) for row in rows]
        conn.close()
        return jsonify({"status": "success", "data": data, "updated_at": get_updated_at('bar_rates.db')})
    except FileNotFoundError as e:
        logging.error(f"Database file not found: {str(e)}")
        return jsonify({"status": "error", "message": "Database file not found"}), 404
    except sqlite3.Error as e:
        logging.error(f"SQLite error: {str(e)}")
        return jsonify({"status": "error", "message": "Database error"}), 500
    except Exception as e:
        logging.error(f"Unexpected error in get_bar_rates: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/api/db/pms-inventory-raw', methods=['GET', 'OPTIONS'])
@require_any_permission('view_data')
def get_pms_inventory_raw():
    try:
        conn = get_db_connection('pms_inventory_raw.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM pms_inventory')
        rows = cursor.fetchall()
        data = [dict(row) for row in rows]
        conn.close()
        return jsonify({"status": "success", "data": data, "updated_at": get_updated_at('pms_inventory_raw.db')})
    except FileNotFoundError as e:
        logging.error(f"Database file not found: {str(e)}")
        return jsonify({"status": "error", "message": "Database file not found"}), 404
    except sqlite3.Error as e:
        logging.error(f"SQLite error: {str(e)}")
        return jsonify({"status": "error", "message": "Database error"}), 500
    except Exception as e:
        logging.error(f"Unexpected error in get_pms_inventory_raw: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/api/db/cm-inventory-raw', methods=['GET', 'OPTIONS'])
@require_any_permission('view_data')
def get_cm_inventory_raw():
    try:
        conn = get_db_connection('cm_inventory_raw.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM cm_inventory_raw')
        rows = cursor.fetchall()
        data = [dict(row) for row in rows]
        conn.close()
        return jsonify({"status": "success", "data": data, "updated_at": get_updated_at('cm_inventory_raw.db')})
    except FileNotFoundError as e:
        logging.error(f"Database file not found: {str(e)}")
        return jsonify({"status": "error", "message": "Database file not found"}), 404
    except sqlite3.Error as e:
        logging.error(f"SQLite error: {str(e)}")
        return jsonify({"status": "error", "message": "Database error"}), 500
    except Exception as e:
        logging.error(f"Unexpected error in get_cm_inventory_raw: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500 