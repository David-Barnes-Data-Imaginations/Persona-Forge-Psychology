from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json, sqlite3
import pandas as pd
from .config import BASE_EXPORT, E2B_MIRROR_DIR, DB_PATH

@dataclass
class SessionKey:
    patient_id: str
    session_type: str
    session_date: str

    def base_dir(self) -> Path:
        return (BASE_EXPORT / self.patient_id / self.session_type / self.session_date).resolve()


    def cypher_dir(self) -> Path:
        return (BASE_EXPORT / "cypher" / self.patient_id / self.session_type / self.session_date).resolve()

def ensure_dirs(sk: SessionKey) -> tuple[Path, Path]:
    b = sk.base_dir(); c = sk.cypher_dir()
    b.mkdir(parents=True, exist_ok=True)
    c.mkdir(parents=True, exist_ok=True)
    return b, c

def _maybe_mirror_write(local_path: Path, data: bytes | str):
    if not E2B_MIRROR_DIR:
        return
    try:
        mirror_path = Path(E2B_MIRROR_DIR).resolve() / local_path.relative_to(BASE_EXPORT)
        mirror_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, str):
            mirror_path.write_text(data, encoding="utf-8")
        else:
            mirror_path.write_bytes(data)
    except Exception as e:
        print(f"[mirror] skip ({e}) → {local_path}")

def save_csv(df: pd.DataFrame, sk: SessionKey, chunk_index: int) -> Path:
    base, _ = ensure_dirs(sk)
    p = base / f"qa_chunk_{chunk_index}.csv"
    df.to_csv(p, index=False)
    _maybe_mirror_write(p, p.read_bytes())
    return p

# ——— SQLite ———
QAPAIRS_DDL = (
    "CREATE TABLE IF NOT EXISTS qa_pairs ("
    "patient_id TEXT, session_date TEXT, session_type TEXT,"
    "turn_id INTEGER, speaker TEXT, text_raw TEXT, text_clean TEXT,"
    "PRIMARY KEY (patient_id, session_date, session_type, turn_id)"
    ")"
)

def sqlite_upsert_df(df: pd.DataFrame, sk: SessionKey):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as con:
        con.execute(QAPAIRS_DDL)
        # create a temp table then upsert to keep pk intact
        df_tmp = df.copy()
        df_tmp.insert(0, "patient_id", sk.patient_id)
        df_tmp.insert(1, "session_date", sk.session_date)
        df_tmp.insert(2, "session_type", sk.session_type)
        df_tmp.to_sql("_qa_pairs_tmp", con, if_exists="replace", index=False)
        con.execute(
            """
            INSERT INTO qa_pairs
            SELECT * FROM _qa_pairs_tmp
            ON CONFLICT(patient_id, session_date, session_type, turn_id) DO UPDATE SET
            speaker=excluded.speaker,
            text_raw=excluded.text_raw,
            text_clean=excluded.text_clean
            """
        )
        con.execute("DROP TABLE _qa_pairs_tmp")
    # mirror DB file if desired
    try:
         _maybe_mirror_write(DB_PATH, DB_PATH.read_bytes())
    except Exception:
        pass

# ——— Graph‑JSON ———
def write_graph_json(payload: dict, sk: SessionKey, chunk_index: int) -> Path:
    base, _ = ensure_dirs(sk)
    p = base / f"graph_chunk_{chunk_index}.json"
    s = json.dumps(payload, ensure_ascii=False, indent=2)
    p.write_text(s, encoding="utf-8")
    _maybe_mirror_write(p, s)
    return p

# ——— Cypher ———
def write_cypher(text: str, sk: SessionKey, chunk_index: int) -> Path:
    _, cdir = ensure_dirs(sk)
    p = cdir / f"chunk_{chunk_index}.cypher"
    p.write_text(text, encoding="utf-8")
    _maybe_mirror_write(p, text)
    return p