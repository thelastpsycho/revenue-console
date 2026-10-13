"""Read-only administration overview. Never returns credentials or local paths."""
import os
from datetime import datetime, timezone
from flask import Blueprint, current_app, jsonify
from ..infrastructure.paths import get_data_path
from ..revenue import booking_events, rms_budget, report_cache
from ..revenue.yield_engine import ROOM_CAPS
from ..integrations.pms.fast_allotment_updater import LABEL_BY_CHECKBOX_VALUE

bp = Blueprint('administration', __name__)


@bp.route('/api/administration/overview')
def overview():
    files = [
        ('Booking history', 'booking_events.db'), ('Revenue budget', 'rms_budget.db'),
        ('PMS inventory', 'pms_inventory_processed.db'), ('Channel inventory', 'cm_inventory_processed.db'),
        ('Combined inventory', 'combined_inventory.db'), ('Yield allocation', 'inventory_allocation.db'),
        ('Forecast cache', 'rms_forecast_cache.db'), ('Stop-sale settings', 'stop_sale.db'),
    ]
    health = []
    for label, filename in files:
        path = get_data_path(filename)
        try:
            st = os.stat(path)
            updated = datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat()
            age = (datetime.now(timezone.utc).timestamp() - st.st_mtime) / 60
            health.append({'name': label, 'available': True, 'updatedAt': updated,
                           'sizeBytes': st.st_size, 'ageMinutes': round(age,1)})
        except FileNotFoundError:
            health.append({'name': label, 'available': False, 'updatedAt': None, 'sizeBytes': None, 'ageMinutes': None})
    auth = current_app.extensions['operator_auth']
    return jsonify({'status':'success', 'dataHealth': health,
        'mappings': {'roomTypes': LABEL_BY_CHECKBOX_VALUE, 'roomCapacities': ROOM_CAPS,
                     'budgetSegments': rms_budget.MARKET_ID_BY_SEGMENT,
                     'channelGroups': [{'id': key, 'label': label} for key, label in booking_events.BUCKET_ORDER]},
        'access': {'configured': auth['configured'], 'developmentMode': auth['dev_mode'], 'model': 'Shared operator PIN',
                   'sessionHours': 8},
        'backups': {'managed': False, 'message': 'No managed backup service is configured in this app. Verify external backups with your system administrator.'},
        'reportTimings': report_cache.timings()})
