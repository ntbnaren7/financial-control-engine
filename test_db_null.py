import sqlite3
conn = sqlite3.connect(':memory:')
c = conn.cursor()
c.execute("""
CREATE TABLE obs (
    provider TEXT,
    ref TEXT,
    type TEXT,
    version TEXT,
    UNIQUE(provider, ref, type, version)
)
""")
c.execute("INSERT INTO obs VALUES ('p', 'r', 't', NULL)")
try:
    c.execute("INSERT INTO obs VALUES ('p', 'r', 't', NULL)")
    print("NULL allowed twice!")
except Exception as e:
    print(f"Error: {e}")

try:
    c.execute("INSERT INTO obs VALUES ('p', 'r', 't', '')")
    c.execute("INSERT INTO obs VALUES ('p', 'r', 't', '')")
    print("Empty string allowed twice!")
except Exception as e:
    print(f"Empty string error: {e}")
