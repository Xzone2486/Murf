import os
import sqlite3

# Mimic the logic in agent_day_6.py
# agent_day_6.py is in backend/src/
# So we place this script in backend/src/ as well to test relative paths.

print("--- DEBUG SCRIPT START ---")
current_file = os.path.abspath(__file__)
print(f"Current script path: {current_file}")

src_dir = os.path.dirname(current_file)
backend_dir = os.path.dirname(src_dir)
db_path = os.path.join(backend_dir, "fraud_cases.db")

print(f"Calculated DB path: {db_path}")

if os.path.exists(db_path):
    print("SUCCESS: Database file found.")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fraud_cases")
        rows = cursor.fetchall()
        print(f"Row count: {len(rows)}")
        for row in rows:
            print(f"Row: {row}")
        conn.close()
    except Exception as e:
        print(f"ERROR: Could not read database: {e}")
else:
    print("FAILURE: Database file NOT found at calculated path.")
    # List files in backend_dir to see what's there
    print(f"Listing files in {backend_dir}:")
    try:
        print(os.listdir(backend_dir))
    except Exception as e:
        print(f"Could not list directory: {e}")

print("--- DEBUG SCRIPT END ---")
