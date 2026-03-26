import sqlite3
import json

db_path = r"c:\Users\anubhab samanta\OneDrive\Documents\Desktop\FactLens\factlens\backend\data\reports.db"
report_id = "report-20260324094458-07038d"

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT payload_json FROM reports WHERE report_id = ?", (report_id,))
    row = cursor.fetchone()
    if row:
        payload = json.loads(row[0])
        results = payload.get("results", [])
        for res in results:
            if res.get('claim_id') == '4':
                print(json.dumps(res, indent=2))
    else:
        print(f"Report {report_id} not found.")
    conn.close()
except Exception as e:
    print(f"Error: {e}")
