from datetime import date
import pytest
from app.revenue import booking_events as be, rms_budget, rms_forecast as fc, report_cache, rms_workspace
from app.revenue.revenue_briefing import summarise
from test_rms import api_row, client


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(be, 'get_data_path', lambda name: str(tmp_path/name))
    monkeypatch.setattr(rms_budget, 'get_data_path', lambda name: str(tmp_path/name))
    monkeypatch.setattr(be, '_today', lambda: date(2026,10,13))
    with be._db() as conn:
        be._set_meta(conn,'backfillFrom','2023-01-01')
        be._set_meta(conn,'lastSuccessfulSync',be._now())
    def forecast(*args, **kwargs):
        days=[(date(2026,10,13)+__import__('datetime').timedelta(days=i)).isoformat() for i in range(30)]
        return {'hotel':[{'date':d,'roomCount':10} for d in days], 'sections':{'hotel':{'stale':False,'refreshing':False,'fetchedAt':be._now(),'error':None}}}
    monkeypatch.setattr(fc,'cached_forecast',forecast)


def test_briefing_uses_matching_windows_currency_and_budget(client):
    be.upsert([api_row(1,'2026-09-01','2026-10-13','2026-11-12',rate=2000000),
               api_row(2,'2026-09-01','2026-10-13','2026-11-12',rate=120,currency='USD')])
    conn=rms_budget._connect()
    for i in range(30):
        d=(date(2026,10,13)+__import__('datetime').timedelta(days=i)).isoformat()
        conn.execute('INSERT INTO daily_budget VALUES (?,?,?,?,?)',(d,8,'gross',3,3000000))
    conn.commit();conn.close()
    response=client.get('/api/rms/briefing')
    assert response.status_code==200
    a,b=response.get_json()['periods']
    assert a['rooms']==14 and b['rooms']==60
    # Row 2's USD rate (120) converts at the default usdIdrRate (16000) and counts toward revenue/ADR.
    usd_revenue = 120*16000*7
    assert a['occupancy']==20 and a['revenue']==14000000+usd_revenue and a['adr']==pytest.approx((14000000+usd_revenue)/14)
    assert a['idrCoveragePct']==100 and a['budgetGap']==pytest.approx(14000000+usd_revenue-7*3000000)
    assert response.headers['Server-Timing'].startswith('report;dur=')


def test_missing_capacity_or_budget_is_unavailable(client,monkeypatch):
    monkeypatch.setattr(fc,'cached_forecast',lambda *a,**k:{'hotel':[],'sections':{'hotel':{'stale':True,'refreshing':True,'fetchedAt':None,'error':None}}})
    data=client.get('/api/rms/briefing').get_json()
    assert all(p['occupancy'] is None and p['budgetGap'] is None for p in data['periods'])
    assert data['warnings']


def test_cache_hits_and_invalidates_booking_and_setting_changes(client):
    url='/api/rms/pace?start=2026-10-13&end=2026-10-13'
    be.upsert([api_row(1,'2026-09-01','2026-10-13','2026-10-14')])
    client.get(url)  # allow initial budget DB creation
    client.get(url)
    assert client.get(url).headers['X-Report-Cache']=='hit'
    be.upsert([api_row(2,'2026-09-01','2026-10-13','2026-10-14')])
    response=client.get(url)
    assert response.headers['X-Report-Cache']=='miss' and response.get_json()['rows'][0]['rooms']==2
    settings=rms_workspace.get_settings();settings['revenueRules'][0]['breakfast']=0;rms_workspace.save_settings(settings)
    assert client.get(url).headers['X-Report-Cache']=='miss'


def test_cached_results_cannot_be_mutated_by_caller():
    args=('2026-10-13','2026-10-13')
    be.pace_table(*args);be.pace_table(*args)
    rows=be.pace_table(*args);rows[0]['rooms']=999
    assert be.pace_table(*args)[0]['rooms']==0


def test_administration_omits_secrets_and_marks_backup_status(client):
    data=client.get('/api/administration/overview').get_json()
    assert data['backups']['managed'] is False
    assert data['access']['model']=='Shared operator PIN'
    assert '123456' not in str(data) and 'APP_SESSION_SECRET' not in str(data)
    assert 'reportTimings' in data


def test_budget_write_invalidates_report_cache(client):
    url='/api/rms/pace?start=2026-10-13&end=2026-10-13'
    client.get(url);client.get(url)
    conn=rms_budget._connect()
    conn.execute('INSERT INTO daily_budget VALUES (?,?,?,?,?)',('2026-10-13',8,'gross',1,5000000))
    conn.commit();conn.close()
    response=client.get(url)
    assert response.headers['X-Report-Cache']=='miss'
    assert response.get_json()['rows'][0]['budgetRevenue']==5000000


def test_failed_calculation_is_never_cached():
    calls=[]
    @report_cache.cached_report
    def calculate():
        calls.append(1)
        if len(calls)==1: raise ValueError('temporary failure')
        return {'result':1}
    with pytest.raises(ValueError): calculate()
    assert calculate()=={'result':1}
    assert calculate()=={'result':1}
    assert len(calls)==2
