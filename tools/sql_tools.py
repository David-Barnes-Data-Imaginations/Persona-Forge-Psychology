from smolagents import Tool

class WriteQAtoSQLite(Tool):
    name = "WriteQAtoSQLite"
    description = "Insert a QA pair into the SQLite database."
    inputs = {"qa": "dict"}
    output_type = "str"

    def run(self, qa: dict) -> str:
        import sqlite3, os
        db_path = "./export/therapy.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS qa_pairs
                       (patient_id TEXT, session_date TEXT,
                        question TEXT, answer TEXT)""")
        cur.execute("INSERT INTO qa_pairs VALUES (?, ?, ?, ?)",
                    (qa.get("patient_id"),
                     qa.get("session_date"),
                     qa.get("question"),
                     qa.get("answer")))
        conn.commit(); conn.close()
        return f"Inserted QA for {qa.get('patient_id')}"

class QuerySQLite(Tool):
    name = "QuerySQLite"
    description = "Run a SQL query on the therapy.db"
    inputs = {"sql": "str"}
    output_type = "list"

    def forward(self, sql: str):
        import sqlite3
        conn = sqlite3.connect("./export/therapy.db")
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        conn.close()
        return rows