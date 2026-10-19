import os
import sqlite3
import json

db_path = "data/dakota.db"
if os.path.exists(db_path):
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    tables = [t[0] for t in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print("Tables in data/dakota.db:")
    for t in tables:
        count = cur.execute(f"SELECT count(*) FROM [{t}]").fetchone()[0]
        print(f"  {t}: {count} rows")
        # Print column names
        cols = [c[1] for c in cur.execute(f"PRAGMA table_info([{t}])").fetchall()]
        print(f"    columns: {cols[:8]}")

# Check other files in data/
print("\nScanning data/ subdirectories for datasets/news/labels/evidence:")
for root, dirs, files in os.walk("data"):
    # skip large cache
    if "cache" in root:
        continue
    for f in files:
        if f.endswith((".json", ".csv", ".jsonl", ".txt")):
            full = os.path.join(root, f)
            sz = os.path.getsize(full)
            print(f"  {full} ({sz} bytes)")
