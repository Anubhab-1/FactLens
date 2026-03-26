import sqlite3
import json

db_path = r"c:\Users\anubhab samanta\OneDrive\Documents\Desktop\FactLens\factlens\backend\data\reports.db"

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT report_id, status, created_at, payload_json FROM reports ORDER BY created_at DESC LIMIT 5")
    rows = cursor.fetchall()
    for row in rows:
        report_id, status, created_at, payload_json = row
        print(f"Report: {report_id} | Status: {status} | Created: {created_at}")
        payload = json.loads(payload_json)
        results = payload.get("results", [])
        print(f"  Results Count: {len(results)}")
        if status == "error":
            print(f"  Error Message: {payload.get('error')}")
        print("-" * 20)
    conn.close()
except Exception as e:
    print(f"Error: {e}")
