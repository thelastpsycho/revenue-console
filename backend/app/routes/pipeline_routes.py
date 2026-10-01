from flask import Blueprint, jsonify, Response, request, stream_with_context
import threading
import json

from ..pipeline import runner as pipeline_runner

bp = Blueprint('pipeline', __name__)


@bp.route('/api/pipeline/steps', methods=['GET'])
def get_pipeline_steps():
    return jsonify({"status": "success", "steps": pipeline_runner.STEPS})


@bp.route('/api/pipeline/status', methods=['GET'])
def pipeline_status():
    return jsonify({
        "status": "success",
        "active": pipeline_runner.pipeline_active,
        "current_step": pipeline_runner.pipeline_current_step,
        "error": pipeline_runner.pipeline_error,
    })


@bp.route('/api/pipeline/start', methods=['POST'])
def start_pipeline():
    data = request.get_json(silent=True) or {}
    # pmsUsername/pmsPassword/dedgeUsername/dedgePassword are optional here - each
    # falls back to the PMS_USERNAME/PMS_PASSWORD/DEDGE_USERNAME/DEDGE_PASSWORD env
    # vars inside the underlying scrape/allotment/BAR functions when omitted.
    required = ['startDate', 'yieldConfig']
    missing = [k for k in required if not data.get(k)]
    if missing:
        return jsonify({"status": "error", "message": f"Missing required field(s): {', '.join(missing)}"}), 400

    if not pipeline_runner.try_acquire():
        return jsonify({"status": "error", "message": "A pipeline run is already in progress"}), 409

    # Drain any stale messages left over from a previous run before starting.
    while not pipeline_runner.pipeline_queue.empty():
        try:
            pipeline_runner.pipeline_queue.get_nowait()
        except Exception:
            break

    config = {
        "pmsUsername": data.get("pmsUsername"),
        "pmsPassword": data.get("pmsPassword"),
        "dedgeUsername": data.get("dedgeUsername"),
        "dedgePassword": data.get("dedgePassword"),
        "startDate": data["startDate"],
        "headless": data.get("headless"),
        "yieldConfig": data["yieldConfig"],
        # Optional: which of the 7 steps to run (missing/omitted = all enabled),
        # and which rooms the allotment/BAR steps should cover.
        "steps": data.get("steps"),
        "allotmentRoomTypes": data.get("allotmentRoomTypes"),
        "barRooms": data.get("barRooms"),
        "resetCheckpoint": data.get("resetCheckpoint") is True,
        "skipUnchanged": data.get("skipUnchanged", True) is not False,
        "barSkipUnchanged": data.get("barSkipUnchanged", True) is not False,
    }
    thread = threading.Thread(target=pipeline_runner.run_pipeline, args=(config,))
    thread.daemon = True
    thread.start()

    return jsonify({"status": "success", "message": "Pipeline started"})


@bp.route('/api/pipeline/stream')
def stream_pipeline_logs():
    def generate():
        while True:
            msg = pipeline_runner.pipeline_queue.get()
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


@bp.route('/api/pipeline/stop', methods=['POST'])
def stop_pipeline():
    """Best-effort: interrupts between steps (checked before each step
    begins), or mid-step only during the allotment step (the only stage that
    already calls check_stop_and_pause() internally). Cannot interrupt
    mid-step during scrape_pms, scrape_cm, combine, yield, verify, or bar."""
    pipeline_runner.allotment_run_control.stop_event.set()
    return jsonify({"status": "success", "message": "Stop requested (best-effort - see route docstring for exact limits)"})
