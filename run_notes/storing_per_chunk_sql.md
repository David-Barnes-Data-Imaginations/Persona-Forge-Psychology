- Your SQL tools already do:
    - exporter = ExportWriter(self.sandbox, C.PATIENT_ID, C.SESSION_TYPE, C.SESSION_DATE)
    - info = exporter.write_sql("therapy.db")
    - sqlite3.connect(info["db_path"]) ← this now reliably points to the host mirror path

Table schema for “chunks” If you want to store per-chunk rows instead of QA pairs, use a minimal table like:
``` sql
-- SQL to initialize (run once)
CREATE TABLE IF NOT EXISTS qa_chunks (
  patient_id   TEXT NOT NULL,
  session_type TEXT NOT NULL,
  session_date TEXT NOT NULL,
  chunk_id     INTEGER NOT NULL,
  csv_rows     INTEGER DEFAULT 0,
  graph_nodes  INTEGER DEFAULT 0,
  payload_json TEXT,               -- optional: raw JSON for the chunk
  PRIMARY KEY (patient_id, session_type, session_date, chunk_id)
);
```
Then upsert a row per processed chunk:
``` python
# Python
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("""
  CREATE TABLE IF NOT EXISTS qa_chunks (
    patient_id   TEXT NOT NULL,
    session_type TEXT NOT NULL,
    session_date TEXT NOT NULL,
    chunk_id     INTEGER NOT NULL,
    csv_rows     INTEGER DEFAULT 0,
    graph_nodes  INTEGER DEFAULT 0,
    payload_json TEXT,
    PRIMARY KEY (patient_id, session_type, session_date, chunk_id)
  )
""")
cur.execute("""
  INSERT INTO qa_chunks (patient_id, session_type, session_date, chunk_id, csv_rows, graph_nodes, payload_json)
  VALUES (?, ?, ?, ?, ?, ?, ?)
  ON CONFLICT(patient_id, session_type, session_date, chunk_id)
  DO UPDATE SET
    csv_rows=excluded.csv_rows,
    graph_nodes=excluded.graph_nodes,
    payload_json=excluded.payload_json
""", (pid, stype, sdate, k, csv_rows, graph_nodes, payload_json))
conn.commit()
conn.close()
```
Why this solves the sandbox/host SQLite issue
- The Python process runs on your host, so sqlite3 must open a host path. We guarantee that by returning the host mirror (./workspace/exports/therapy.db).
- If the E2B sandbox is active, we also create a zero-byte mirror at /workspace/exports/therapy.db inside the sandbox so your tools or inspector inside the sandbox “see” the file. You don’t need to open the DB from inside the sandbox unless you run queries there too.

If you prefer to run SQL queries inside the sandbox process, you’ll need to execute them via the sandbox API (e.g., running a Python snippet in the sandbox) using the sandbox path. But with the above, your current host-side tools will work consistently.
