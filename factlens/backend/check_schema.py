import sqlite3

db_path = r"c:\Users\anubhab samanta\OneDrive\Documents\Desktop\FactLens\factlens\backend\data\reports.db"

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(reports)")
    columns = cursor.fetchall()
    for col in columns:
        print(col)
    conn.close()
except Exception as e:
    print(f"Error: {e}")
