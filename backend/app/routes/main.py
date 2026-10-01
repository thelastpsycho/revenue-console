from flask import Blueprint, jsonify, Response, request, stream_with_context
from ..integrations.pms.inventory_scraper import scrape_pms_inventory
from ..inventory.inventory_combiner import combine_inventory_files
from ..revenue.yield_engine import load_and_clean_data, apply_yield_matrix, apply_custom_yield
from ..inventory.channel_manager_processor import process_cm_inventory
from ..integrations.dedge.inventory_scraper import scrape_cm_inventory
from ..integrations.pms.allotment_updater import update_allotmet
from ..integrations.pms.other_room_allotment_updater import update_rest_allotment
from ..integrations.dedge.bar_updater import update_bar
from ..shared import log_queue, allotment_run_control
from ..pipeline import runner as pipeline_runner
import queue
import threading
import time
import sys
from io import StringIO
import logging
from werkzeug.utils import secure_filename
import os
import json
import sqlite3
import pandas as pd
from ..infrastructure.paths import get_data_dir, get_data_path

bp = Blueprint('main', __name__)

# Global variables for scraping progress
scraping_active = False
scraping_error = None
scraping_progress = queue.Queue()

UPLOAD_FOLDER = get_data_dir()
ALLOWED_EXTENSIONS = {'xlsx'}

class RealTimeStringIO(StringIO):
    def __init__(self, queue):
        super().__init__()
        self.queue = queue
        self._is_capturing = False

    def write(self, text):
        if not self._is_capturing:
            self._is_capturing = True
            try:
                if text.strip():  # Only process non-empty lines
                    self.queue.put(text.strip())
            finally:
                self._is_capturing = False

def scrape_with_progress(start_date=None, username=None, password=None):
    global scraping_active, scraping_error
    try:
        # Redirect stdout to capture print statements
        old_stdout = sys.stdout
        sys.stdout = RealTimeStringIO(scraping_progress)

        result = scrape_pms_inventory(start_date, username=username, password=password)
        
        # Restore stdout
        sys.stdout = old_stdout
        
        if result is not None:
            scraping_progress.put({"status": "success", "message": "Scraping completed successfully"})
        else:
            scraping_error = "Scraping failed"
            scraping_progress.put({"status": "error", "message": "Scraping failed"})
    except Exception as e:
        scraping_error = str(e)
        scraping_progress.put({"status": "error", "message": str(e)})
    finally:
        scraping_active = False

@bp.route('/api/health')
def health_check():
    return jsonify({"status": "healthy"})

@bp.route('/api/scrape', methods=['POST'])
def trigger_scrape():
    global scraping_active, scraping_error
    if pipeline_runner.pipeline_active:
        return jsonify({"status": "error", "message": "A pipeline run is currently in progress; please wait for it to finish."}), 409
    if scraping_active:
        return jsonify({"status": "error", "message": "Scraping already in progress"}), 409
    
    # Get start date and credentials from request
    start_date = request.json.get('startDate')
    if not start_date:
        return jsonify({"status": "error", "message": "Start date is required"}), 400

    # Falls back to PMS_USERNAME / PMS_PASSWORD env vars inside scrape_pms_inventory when omitted.
    username = request.json.get('username')
    password = request.json.get('password')

    # Reset error state
    scraping_error = None
    scraping_active = True
    
    # Clear the queue
    while not scraping_progress.empty():
        try:
            scraping_progress.get_nowait()
        except queue.Empty:
            break
    
    scraping_thread = threading.Thread(target=scrape_with_progress, args=(start_date, username, password))
    scraping_thread.daemon = True
    scraping_thread.start()
    
    return jsonify({"status": "success", "message": "Scraping started"})

@bp.route('/api/scrape/stream')
def scrape_stream():
    def generate():
        global scraping_error
        while scraping_active or not scraping_progress.empty():
            try:
                if not scraping_progress.empty():
                    message = scraping_progress.get()
                    yield f"data: {json.dumps(message)}\n\n"
                elif scraping_error:
                    yield f"data: {json.dumps({'status': 'error', 'message': scraping_error})}\n\n"
                    break
                else:
                    yield f"data: {json.dumps({'status': 'pending'})}\n\n"
                time.sleep(0.1)
            except Exception as e:
                yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"
                break
        if not scraping_error:
            yield f"data: {json.dumps({'status': 'complete', 'message': 'Scraping completed successfully'})}\n\n"

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )

@bp.route('/api/combine-inventory', methods=['POST'])
def trigger_combine():
    if pipeline_runner.pipeline_active:
        return jsonify({"status": "error", "message": "A pipeline run is currently in progress; please wait for it to finish."}), 409
    try:
        print("Starting inventory combination process...")
        
        # Check if required files exist
        pms_db_path = get_data_path('pms_inventory_processed.db')
        cm_db_path = get_data_path('cm_inventory_processed.db')
        
        if not os.path.exists(pms_db_path):
            return jsonify({
                "status": "error",
                "message": "PMS inventory database not found. Please run scraping first."
            }), 400
            
        if not os.path.exists(cm_db_path):
            return jsonify({
                "status": "error",
                "message": "CM inventory database not found. Please upload and process CM Excel file first."
            }), 400
        
        print(f"Found required databases: PMS={pms_db_path}, CM={cm_db_path}")
        
        result = combine_inventory_files()
        
        # Verify the combined database was created
        combined_db_path = get_data_path('combined_inventory.db')
        if not os.path.exists(combined_db_path):
            return jsonify({
                "status": "error",
                "message": "Failed to create combined inventory database"
            }), 500
            
        # Verify data was written
        conn = sqlite3.connect(combined_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM combined_inventory")
        count = cursor.fetchone()[0]
        conn.close()
        
        if count == 0:
            return jsonify({
                "status": "error",
                "message": "No data was written to the combined inventory database"
            }), 500
            
        print(f"Successfully combined inventory with {count} rows")
        
        return jsonify({
            "status": "success",
            "message": "Inventory combination completed successfully",
            "data": str(result)
        })
    except Exception as e:
        print(f"Error in combine inventory: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@bp.route('/api/yield', methods=['POST'])
def trigger_yield():
    if pipeline_runner.pipeline_active:
        return jsonify({"status": "error", "message": "A pipeline run is currently in progress; please wait for it to finish."}), 409
    try:
        print("Starting yield calculation process...")
        
        # Check if combined inventory exists
        combined_db_path = get_data_path('combined_inventory.db')
        if not os.path.exists(combined_db_path):
            return jsonify({
                "status": "error",
                "message": "Combined inventory database not found. Please run combine inventory first."
            }), 400

        # Call the main function which handles the entire process
        from ..revenue.yield_engine import main
        result = main()
        
        if result is None:
            return jsonify({
                "status": "error",
                "message": "Failed to process yield calculation"
            }), 500
        
        # Verify the database was created
        db_path = get_data_path('inventory_allocation.db')
        if not os.path.exists(db_path):
            return jsonify({
                "status": "error",
                "message": "Failed to create inventory allocation database"
            }), 500

        # Verify the data was written correctly
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM daily_inventory_allocation")
        count = cursor.fetchone()[0]
        conn.close()

        if count == 0:
            return jsonify({
                "status": "error",
                "message": "No data was written to the inventory allocation database"
            }), 500

        # Convert the result to a format that can be serialized to JSON
        result_dict = result.to_dict(orient='records')
        
        return jsonify({
            "status": "success",
            "message": "Yield calculation completed successfully",
            "data": result_dict
        })
    except Exception as e:
        print(f"Error in yield calculation: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Failed to calculate yield: {str(e)}"
        }), 500

@bp.route('/api/process-cm', methods=['POST'])
def trigger_process_cm():
    try:
        result = process_cm_inventory()
        return jsonify({
            "status": "success",
            "message": "CM inventory processing completed successfully",
            "data": str(result)
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@bp.route('/api/scrape-cm/stream')
def stream_scrape_cm_logs():
    """Stream CM scrape logs using Server-Sent Events (shares log_queue with the
    D-EDGE allotment/BAR flows)."""
    return Response(
        stream_with_context(log_stream()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )

@bp.route('/api/scrape-cm', methods=['POST'])
def trigger_scrape_cm():
    """Log into D-EDGE / Availpro, export the Rooms planning grid, and process it.

    Credentials fall back to the DEDGE_USERNAME / DEDGE_PASSWORD env vars when
    omitted from the request body. days defaults to 100 inside scrape_cm_inventory
    to match the PMS scraper's range. Progress streams over /api/scrape-cm/stream
    (scrape_cm_inventory's own step logs already push onto the shared log_queue).
    """
    if pipeline_runner.pipeline_active:
        return jsonify({"status": "error", "message": "A pipeline run is currently in progress; please wait for it to finish."}), 409
    try:
        data = request.get_json(silent=True) or {}
        username = data.get('dedgeUsername')
        password = data.get('dedgePassword')
        start_date = data.get('startDate')
        headless = data.get('headless')

        def run():
            try:
                log_queue.put({'type': 'info', 'message': 'Starting CM export from D-EDGE / Availpro...'})
                result = scrape_cm_inventory(start_date=start_date, username=username, password=password, headless=headless)
                log_queue.put({'type': 'success', 'message': result or 'CM inventory processing completed successfully'})
            except Exception as e:
                log_queue.put({'type': 'error', 'message': str(e)})
            finally:
                log_queue.put(None)

        thread = threading.Thread(target=run)
        thread.daemon = True
        thread.start()

        return jsonify({
            "status": "success",
            "message": "CM scrape started"
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@bp.route('/api/custom-yield', methods=['POST'])
def trigger_custom_yield():
    if pipeline_runner.pipeline_active:
        return jsonify({"status": "error", "message": "A pipeline run is currently in progress; please wait for it to finish."}), 409
    try:
        print("Starting custom yield calculation process...")
        
        # Get configuration from request
        config = request.json
        if not config:
            return jsonify({
                "status": "error",
                "message": "No configuration provided"
            }), 400

        # Validate required configuration
        required_configs = {
            'demand_bins': list,
            'demand_labels': list,
            'very_low_threshold_pct': (int, float),
            'low_threshold_pct': (int, float),
            'room_caps': dict,
            'deluxe_override_occupancy': (int, float),
            'deluxe_override_premiere': (int, float),
            'deluxe_override_amount': (int, float)
        }

        for key, expected_type in required_configs.items():
            if key not in config:
                return jsonify({
                    "status": "error",
                    "message": f"Missing required configuration: {key}"
                }), 400
            if not isinstance(config[key], expected_type):
                return jsonify({
                    "status": "error",
                    "message": f"Invalid type for {key}. Expected {expected_type}, got {type(config[key])}"
                }), 400

        # Optional: shift the BAR base matrix N whole ranks (positive = more
        # expensive, negative = cheaper) before scarcity escalation. Defaults
        # to 0 (no shift) for backward compatibility with older clients.
        bar_level_shift = config.get('bar_level_shift', 0)
        if not isinstance(bar_level_shift, (int, float)) or isinstance(bar_level_shift, bool):
            return jsonify({
                "status": "error",
                "message": f"Invalid type for bar_level_shift. Expected number, got {type(bar_level_shift)}"
            }), 400
        bar_level_shift = int(bar_level_shift)

        # Check if combined inventory exists
        combined_db_path = get_data_path('combined_inventory.db')
        if not os.path.exists(combined_db_path):
            return jsonify({
                "status": "error",
                "message": "Combined inventory database not found. Please run combine inventory first."
            }), 400

        # Run the compute-and-write step (load, yield, persist to
        # inventory_allocation.db) via the shared yielder helper, so the
        # automated pipeline can reuse the exact same logic without going
        # through this HTTP route.
        config['bar_level_shift'] = bar_level_shift
        try:
            result = apply_custom_yield(config)
        except (FileNotFoundError, ValueError) as e:
            return jsonify({
                "status": "error",
                "message": str(e)
            }), 400

        # Convert the result to a format that can be serialized to JSON
        result_dict = result.to_dict(orient='records')
        
        return jsonify({
            "status": "success",
            "message": "Custom yield calculation completed successfully",
            "data": result_dict
        })
    except Exception as e:
        print(f"Error in custom yield calculation: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Failed to calculate custom yield: {str(e)}"
        }), 500

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@bp.route('/api/upload-cm-excel', methods=['POST'])
def upload_cm_excel():
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'No selected file'}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename('cm_upload.xlsx')
        save_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(save_path)
        return jsonify({'status': 'success', 'message': 'File uploaded successfully'})
    return jsonify({'status': 'error', 'message': 'Invalid file type'}), 400

def log_stream():
    """Generator function to stream logs"""
    while True:
        try:
            # Get log message from queue
            log_data = log_queue.get()
            if log_data is None:  # None is used as a signal to stop
                break
            # Yield the log data as SSE
            yield f"data: {json.dumps(log_data)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

@bp.route('/api/update-allotment/stream')
def stream_allotment_logs():
    """Stream allotment update logs using Server-Sent Events"""
    return Response(
        stream_with_context(log_stream()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )

@bp.route('/api/update-allotment', methods=['POST'])
def trigger_update_allotment():
    """Trigger allotment update process"""
    if pipeline_runner.pipeline_active:
        return jsonify({"status": "error", "message": "A pipeline run is currently in progress; please wait for it to finish."}), 409
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        room_type = data.get('room_type', 'deluxe')
        max_dates = data.get('max_dates')
        headless = data.get('headless')
        skip_unchanged = data.get('skip_unchanged', True)
        # Falls back to PMS_USERNAME / PMS_PASSWORD env vars inside update_allotmet when omitted.

        if room_type not in ('deluxe', 'premiere'):
            return jsonify({
                'status': 'error',
                'message': 'room_type must be "deluxe" or "premiere"'
            }), 400

        # Start update process in a separate thread
        def update_process():
            try:
                # Add initial log
                log_queue.put({
                    'type': 'info',
                    'message': f'Starting {room_type} allotment update process...'
                })

                # Call the update function
                result = update_allotmet(username=username, password=password, room_type=room_type, max_dates=max_dates, headless=headless, skip_unchanged=skip_unchanged)

                if result:
                    log_queue.put({
                        'type': 'success',
                        'message': 'Allotment updated successfully!'
                    })
                else:
                    log_queue.put({
                        'type': 'error',
                        'message': 'Failed to update allotment'
                    })
            except Exception as e:
                log_queue.put({
                    'type': 'error',
                    'message': f'Error during update: {str(e)}'
                })
            finally:
                # Signal the end of streaming
                log_queue.put(None)

        # Start the update process in a background thread
        allotment_run_control.reset()
        thread = threading.Thread(target=update_process)
        thread.start()

        return jsonify({
            'status': 'success',
            'message': 'Update process started'
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@bp.route('/api/update-allotment/stop', methods=['POST'])
def stop_update_allotment():
    """Request the running Deluxe/Premiere/Rest allotment update to stop"""
    allotment_run_control.stop_event.set()
    return jsonify({'status': 'success', 'message': 'Stop requested'})

@bp.route('/api/update-allotment/pause', methods=['POST'])
def pause_update_allotment():
    """Request the running Deluxe/Premiere/Rest allotment update to pause"""
    allotment_run_control.pause_event.set()
    return jsonify({'status': 'success', 'message': 'Pause requested'})

@bp.route('/api/update-allotment/resume', methods=['POST'])
def resume_update_allotment():
    """Resume a paused Deluxe/Premiere/Rest allotment update"""
    allotment_run_control.pause_event.clear()
    return jsonify({'status': 'success', 'message': 'Resume requested'})

@bp.route('/api/update-rest-allotment', methods=['POST'])
def trigger_update_rest_allotment():
    """Trigger allotment update process for the 11 room types other than Deluxe/Premiere"""
    if pipeline_runner.pipeline_active:
        return jsonify({"status": "error", "message": "A pipeline run is currently in progress; please wait for it to finish."}), 409
    try:
        data = request.get_json()
        # Falls back to PMS_USERNAME / PMS_PASSWORD env vars inside update_rest_allotment when omitted.
        username = data.get('username')
        password = data.get('password')
        max_dates = data.get('max_dates')
        headless = data.get('headless')
        skip_unchanged = data.get('skip_unchanged', True)

        # Start update process in a separate thread
        def update_process():
            try:
                log_queue.put({
                    'type': 'info',
                    'message': 'Starting allotment update process for the rest of the room types...'
                })

                result = update_rest_allotment(username=username, password=password, max_dates=max_dates, headless=headless, skip_unchanged=skip_unchanged)

                if result:
                    log_queue.put({
                        'type': 'success',
                        'message': 'Allotment updated successfully!'
                    })
                else:
                    log_queue.put({
                        'type': 'error',
                        'message': 'Failed to update allotment'
                    })
            except Exception as e:
                log_queue.put({
                    'type': 'error',
                    'message': f'Error during update: {str(e)}'
                })
            finally:
                # Signal the end of streaming
                log_queue.put(None)

        # Start the update process in a background thread
        allotment_run_control.reset()
        thread = threading.Thread(target=update_process)
        thread.start()

        return jsonify({
            'status': 'success',
            'message': 'Update process started'
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@bp.route('/api/update-bar/stream')
def stream_bar_logs():
    """Stream BAR price-level update logs using Server-Sent Events"""
    return Response(
        stream_with_context(log_stream()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )

@bp.route('/api/update-bar', methods=['POST'])
def trigger_update_bar():
    """Trigger the D-EDGE / Availpro BAR price-level update process.

    Reads the yielder's inventory_allocation.db and pushes BAR levels onto the
    extranet. Credentials are optional: they fall back to the DEDGE_USERNAME /
    DEDGE_PASSWORD env vars, and login is skipped entirely when the persistent
    Chrome profile already holds a valid session.
    """
    if pipeline_runner.pipeline_active:
        return jsonify({"status": "error", "message": "A pipeline run is currently in progress; please wait for it to finish."}), 409
    try:
        data = request.get_json(silent=True) or {}
        username = data.get('username')
        password = data.get('password')
        rooms = data.get('rooms', ['deluxe', 'premiere'])
        dry_run = bool(data.get('dry_run', False))
        max_levels_per_room = data.get('max_levels_per_room')
        headless = data.get('headless')
        reset_checkpoint = data.get('resetCheckpoint', False)
        if not isinstance(reset_checkpoint, bool):
            return jsonify({'status': 'error', 'message': 'resetCheckpoint must be boolean'}), 400
        skip_unchanged = data.get('barSkipUnchanged', True) is not False

        if isinstance(rooms, str):
            rooms = [rooms]
        invalid = [r for r in rooms if r not in ('deluxe', 'premiere')]
        if invalid:
            return jsonify({
                'status': 'error',
                'message': f'Invalid room(s) {invalid}; allowed values are "deluxe" and "premiere"'
            }), 400

        # Start update process in a separate thread
        def update_process():
            try:
                log_queue.put({
                    'type': 'info',
                    'message': f'Starting BAR price-level update ({", ".join(rooms)})'
                             + (' [dry-run]' if dry_run else '') + '...'
                })

                result = update_bar(
                    username=username,
                    password=password,
                    rooms=tuple(rooms),
                    dry_run=dry_run,
                    max_levels_per_room=max_levels_per_room,
                    headless=headless,
                    reset_checkpoint=reset_checkpoint,
                    skip_unchanged=skip_unchanged,
                )

                if result:
                    log_queue.put({
                        'type': 'success',
                        'message': 'BAR price levels updated successfully!'
                    })
                else:
                    log_queue.put({
                        'type': 'error',
                        'message': 'Failed to update BAR price levels'
                    })
            except Exception as e:
                log_queue.put({
                    'type': 'error',
                    'message': f'Error during BAR update: {str(e)}'
                })
            finally:
                # Signal the end of streaming
                log_queue.put(None)

        thread = threading.Thread(target=update_process)
        thread.start()

        return jsonify({
            'status': 'success',
            'message': 'BAR update process started'
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
