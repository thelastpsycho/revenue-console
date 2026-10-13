import json,tempfile,time
from datetime import date,timedelta
from app.revenue import booking_events as be,rms_budget,rms_reports
# Run with PYTHONPATH=backend. Synthetic data stays in a temporary directory.
with tempfile.TemporaryDirectory() as root:
    be.get_data_path=lambda name:root+'/'+name
    rms_budget.get_data_path=be.get_data_path
    today=date(2026,10,13);be._today=lambda:today
    rows=[]
    for i in range(12000):
        arrival=today+timedelta(days=(i%120)-40-(364 if i>=6000 else 0))
        rows.append({'ReservationId':i,'IsMasterFolio':True,'ReservationDate':(arrival-timedelta(days=45)).isoformat(),'ArrivalDate':arrival.isoformat(),'DepartureDate':(arrival+timedelta(days=4)).isoformat(),'Nights':4,'ReservationStatus':'D','TypeId':'DLT' if i%2 else 'PRKG','RateType':'BAR','RateId':str(i%20),'MarketId':i%10,'MarketDescription':'Segment '+str(i%10),'RoomRate':2000000,'Currency':'IDR','CompanyName':'Agoda.com','CompanyId':1})
    be.upsert(rows)
    with be._db() as conn:be._set_meta(conn,'backfillFrom','2023-01-01')
    results={}
    for name,call in [('pace30',lambda:be.pace_table(today.isoformat(),(today+timedelta(days=29)).isoformat())),('reports30',lambda:rms_reports.build_reports(today.isoformat(),(today+timedelta(days=29)).isoformat()))]:
        durations=[]
        for _ in range(4):
            start=time.perf_counter();call();durations.append(round((time.perf_counter()-start)*1000,2))
        results[name]={'coldMs':durations[0],'warmMs':durations[1:]}
    print(json.dumps({'reservations':len(rows),'results':results},indent=2))
