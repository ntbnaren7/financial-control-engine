import os
from sqlalchemy import create_engine, text
from src.config.settings import FCESettings

url = FCESettings.load().database.url.get_secret_value()
engine = create_engine(url)

payload_id = 'd0eb6b14-1726-41ec-b9c2-1e73ca399792'

with engine.connect() as conn:
    print("--- INGESTION PAYLOAD ---")
    res = conn.execute(text(f"select status, error_message from substrate_ingestion_payloads where payload_id = '{payload_id}';"))
    for r in res:
        print(r)

    print("\n--- EVIDENCE & OBSERVATION ---")
    res = conn.execute(text(f"select evidence_id from v2_evidence where payload_hash like '%%pay_89143%%';"))
    for r in res:
        print(r)
        
    res = conn.execute(text(f"select observation_id, observed_state from v2_observations where provider_reference = 'pay_89143';"))
    obs_id = None
    for r in res:
        print(r)
        obs_id = r[0]
        
    if obs_id:
        print("\n--- CONTROL EVENTS ---")
        res = conn.execute(text(f"select event_id, event_type, status from v2_control_events;"))
        for r in res:
            print(r)
            
        print("\n--- CONTROL INCIDENTS ---")
        res = conn.execute(text(f"select incident_id, state from v2_active_incidents;"))
        for r in res:
            print(r)
