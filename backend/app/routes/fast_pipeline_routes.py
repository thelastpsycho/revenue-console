"""Routes for the API-based pipeline (pipeline/fast_runner.py). Kept separate
from routes/pipeline_routes.py so the existing Selenium pipeline and its route
handlers are never touched by this work."""

from flask import Blueprint, jsonify, Response, request, stream_with_context
import threading
import json

from ..pipeline import fast_runner
from ..pipeline import fast_pipeline_log_store
from ..pipeline import fast_pipeline_schedule

bp = Blueprint('fast_pipeline', __name__)


def _launch(config):
    """Start run_pipeline in a background thread. Caller must already hold the
    lock from fast_runner.try_acquire()."""
    while not fast_runner.pipeline_queue.empty():
        try:
            fast_runner.pipeline_queue.get_nowait()
        except Exception:
            break
    thread = threading.Thread(target=fast_runner.run_pipeline, args=(config,))
    thread.daemon = True
    thread.start()


@bp.route('/api/fast-pipeline/steps', methods=['GET'])
def get_fast_pipeline_steps():
    return jsonify({"status": "success", "steps": fast_runner.STEPS})


@bp.route('/api/fast-pipeline/status', methods=['GET'])
def fast_pipeline_status():
    return jsonify({
        "status": "success",
        "active": fast_runner.pipeline_active,
        "current_step": fast_runner.pipeline_current_step,
        "error": fast_runner.pipeline_error,
    })


@bp.route('/api/fast-pipeline/start', methods=['POST'])
def start_fast_pipeline():
    data = request.get_json(silent=True) or {}
    required = ['startDate', 'yieldConfig']
    missing = [k for k in required if not data.get(k)]
    if missing:
        return jsonify({"status": "error", "message": f"Missing required field(s): {', '.join(missing)}"}), 400

    acquired, reason = fast_runner.try_acquire()
    if not acquired:
        return jsonify({"status": "error", "message": reason}), 409

    config = {
        "pmsUsername": data.get("pmsUsername"),
        "pmsPassword": data.get("pmsPassword"),
        "dedgeUsername": data.get("dedgeUsername"),
        "dedgePassword": data.get("dedgePassword"),
        "startDate": data["startDate"],
        "headless": data.get("headless"),
        "yieldConfig": data["yieldConfig"],
        "steps": data.get("steps"),
        "barRooms": data.get("barRooms"),
        "allotmentRoomTypes": data.get("allotmentRoomTypes"),
        "resetCheckpoint": data.get("resetCheckpoint") is True,
        "skipUnchanged": data.get("skipUnchanged", True) is not False,
        "barSkipUnchanged": data.get("barSkipUnchanged", True) is not False,
        "allotmentDryRun": data.get("allotmentDryRun", True) is not False,
        "allotmentConcurrency": data.get("allotmentConcurrency", 4),
        "companyId": data.get("companyId", 1001),
    }
    _launch(config)

    return jsonify({"status": "success", "message": "Fast pipeline started"})


@bp.route('/api/fast-pipeline/schedule', methods=['GET'])
def get_fast_pipeline_schedule():
    return jsonify({
        "status": "success",
        "schedule": fast_pipeline_schedule.get_state(),
        "lastScheduledRun": fast_pipeline_log_store.latest_run_by_trigger("schedule"),
        "pipelineActive": fast_runner.pipeline_active,
    })


@bp.route('/api/fast-pipeline/schedule', methods=['PUT'])
def update_fast_pipeline_schedule():
    data = request.get_json(silent=True) or {}
    try:
        state = fast_pipeline_schedule.update_settings(data)
    except fast_pipeline_schedule.ScheduleValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except (OSError, ValueError) as exc:
        return jsonify({"status": "error", "message": f"Could not save schedule: {exc}"}), 500
    return jsonify({"status": "success", "schedule": state})


@bp.route('/api/fast-pipeline/schedule/tick', methods=['POST'])
def fast_pipeline_schedule_tick():
    """Polled by the scheduler container (trigger_fast_pipeline.py --managed).
    Starts a run when one is due; otherwise just records the heartbeat."""
    try:
        config, reason = fast_pipeline_schedule.claim_due_run(fast_runner.try_acquire)
    except (OSError, ValueError) as exc:
        return jsonify({"status": "error", "started": False, "message": f"Could not build scheduled run: {exc}"}), 500
    if config is None:
        return jsonify({"status": "success", "started": False, "message": reason})
    _launch(config)
    return jsonify({
        "status": "success",
        "started": True,
        "mode": config["scheduleMode"],
        "message": f"Scheduled {config['scheduleMode']} run started",
    })


@bp.route('/api/fast-pipeline/stream')
def stream_fast_pipeline_logs():
    def generate():
        while True:
            msg = fast_runner.pipeline_queue.get()
            if msg is None:
                break
            yield f"data: {json.dumps(msg)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )


@bp.route('/api/fast-pipeline/history', methods=['GET'])
def fast_pipeline_history():
    limit = request.args.get('limit', 50, type=int)
    return jsonify({"status": "success", "runs": fast_pipeline_log_store.list_runs(limit=limit)})


@bp.route('/api/fast-pipeline/history/<int:run_id>', methods=['GET'])
def fast_pipeline_run_detail(run_id):
    run = fast_pipeline_log_store.get_run(run_id)
    if run is None:
        return jsonify({"status": "error", "message": "Run not found"}), 404
    return jsonify({"status": "success", "run": run, "logs": fast_pipeline_log_store.get_run_logs(run_id)})


@bp.route('/api/fast-pipeline/search', methods=['GET'])
def fast_pipeline_search():
    query = (request.args.get('q') or '').strip()
    if not query:
        return jsonify({"status": "success", "matches": []})
    limit = request.args.get('limit', 200, type=int)
    return jsonify({"status": "success", "matches": fast_pipeline_log_store.search_log_entries(query, limit=limit)})


@bp.route('/api/fast-pipeline/stop', methods=['POST'])
def stop_fast_pipeline():
    """Best-effort: interrupts between steps only. The allotment step's
    concurrent push has no mid-batch stop check (see fast_allotment_updater.py) -
    once it starts it runs to completion."""
    fast_runner.allotment_run_control.stop_event.set()
    return jsonify({"status": "success", "message": "Stop requested (best-effort - see route docstring for exact limits)"})
