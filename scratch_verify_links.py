import sqlite3
conn = sqlite3.connect('tenders.db')
c = conn.cursor()
c.execute("SELECT source, link FROM processed_tenders WHERE status='approved' AND source='CPPP Master Portal (Aggregator)' LIMIT 5")
for r in c.fetchall():
    print(f"Source: {r[0]}")
    print(f"Link: {r[1]}")
    print("---")
