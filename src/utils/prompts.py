from __future__ import annotations
from . import config as C
from .session_paths import session_templates
from src.utils.paths import SBX_DATA_DIR, SBX_EXPORTS_DIR, SBX_DB_DIR

"""
Prompts read sandbox-first path templates from `session_paths.py`.
All write operations during Passes should use these sandbox paths.
PersistenceManager pulls `/workspace/export` back to `./export` on shutdown.

To change where files land, edit `session_paths.session_templates()`
(not these prompt strings).
"""


def build_planning_initial_facts() -> str:
    t = session_templates(C.PATIENT_ID, C.SESSION_TYPE, C.SESSION_DATE)
    return f"""
**Fixed environment facts (SANDBOX paths)**
CSV path template: {t.csv_template}
Graph JSON template: {t.graph_template}
Cypher export dir: {t.cypher_dir}
SQLite DB: {t.sqlite_db}
Therapy transcript: {t.therapy_md}
Psych frameworks: {t.psych_frameworks_md}
Graph schema: {t.graph_schema_json}

 **Placeholders**
 - Use k (an integer) as the current chunk index when calling tools. Do **not** write files directly; call:
   - write_graph_for_chunk(k, graph)
   - write_cypher_for_chunk(k, cypher_text)
   - write_csv_for_chunk(k, csv_text, record_count, columns)
   - search_metadata_chunks(query, top_k=5, kind="metadata|corpus|any", include_notes=true)
 """.strip()

# Export the constant your router expects
PLANNING_INITIAL_FACTS = build_planning_initial_facts()

THERAPY_SYSTEM_PROMPT = r"""
You are a methodical agent that processes THERAPY QA pairs in fixed chunks.
You must always answer in the strict sequence:

Thought:
Code:
Observation:

All Python in the Code block MUST be wrapped in <code>...</code> tags.
Never invent tools. Prefer Python file I/O and sqlite3. Use pandas when helpful.
You MUST keep outputs deterministic and exactly follow the required schemas.

CHUNKING & CONTEXT
- Process at most CHUNK_SIZE QA pairs per iteration (default 50).
- Before each chunk: recall prior insights from memory/psych_metadata if available.
- After each chunk: write a compact summary of decisions & anomalies to `agent_notes` via the provided memory tool if available; otherwise persist locally (JSONL: `states/agent_notes.jsonl`).

PRIVACY
- Replace any explicit names with stable pseudonyms (Therapist_1, Client_###).
- No DOB, addresses, phones, emails.
- Keep only date strings like '2025-08-19' when provided or inferred.

OUTPUT CONTRACTS PER PASS
- Pass A (CLEAN): emit a pandas DataFrame `df_clean` with exactly these columns:
["session_date","session_type","turn_id","speaker","text_raw","text_clean"]

- Pass B (FILE): persist the processed chunk via tools:
  1) CSV → (tool-managed) session export dir
  2) SQLite → /workspace/exports/therapy.db (table: qa_pairs; PK: (patient_id, session_date, session_type, turn_id))
  3) Graph‑JSON → (tool-managed) session export dir

Do **not** write files directly; call the tools. Targets are:
    - CSV: /workspace/exports/{PATIENT_ID}/{SESSION_TYPE}/{SESSION_DATE}/qa_chunk_{k}.csv
    - Graph: /workspace/exports/{PATIENT_ID}/{SESSION_TYPE}/{SESSION_DATE}/graph_chunk_{k}.json

- Pass C (GRAPH): read Graph‑JSON files and generate Cypher to STDOUT and also write to `/workspace/exports/cypher/{PATIENT_ID}/{SESSION_TYPE}/{SESSION_DATE}/chunk_{k}.cypher`.
Do not execute Memgraph here; only generate Cypher text, then call the cypher-writing tool.


OUTPUT CONTRACTS/TOOLS
- Writing is done via tools:
  - write_graph_for_chunk(k, graph_dict)  → validates against schema then persists
  - write_cypher_for_chunk(k, cypher_txt) → writes to cypher/chunk_{k}.cypher
  - document_learning_insights(title, notes_markdown, metadata) → persists insights

VALIDATION
- After each write, print an explicit confirmation with file paths and row counts.


FINALIZATION
- Only when a pass completes for all chunks, call:
<code>final_answer("PASS_COMPLETE")</code>
"""

THERAPY_PASS_A_CLEAN = r"""
ROLE: CLEAN & NORMALIZE QA pairs from a raw transcript file.

INPUTS
- A UTF‑8 text file (e.g., `therapy.md`) containing alternating Therapist/Client blocks.
- Config vars you will set in code:
    PATIENT_ID = "Client_345" (or as provided).
    SESSION_TYPE = "therapy"
    SESSION_DATE = "2025-08-19" # use provided date or a passed‑in value
    CHUNK_SIZE = 50

TASK
1) Parse the transcript into QA pairs with incremental `turn_id` starting at 1.
2) Speakers → one of {"Therapist","Client"}. Map other tags accordingly.
3) `text_clean` rules:
    - Trim whitespace, fix obvious typos when unambiguous (keep semantics)
    - Remove markdown headers/separators, keep quoted user content
    - Preserve meaning; no summarization here
4) Build `df_clean` with columns exactly:
    ["session_date","session_type","turn_id","speaker","text_raw","text_clean"]
    And add `PATIENT_ID` as a separate Python variable (not a column) for Pass B.

MEMORY
- Before chunk: try recalling prior notes (e.g., via `retrieve_metadata` or local JSONL)
- After chunk: append a 1‑3 sentence note describing patterns/edge cases.

OUTPUT
- Print `df_clean.info()` and the first 3 rows for audit.
- Keep `df_clean` in memory for Pass B.
- Do NOT write files in Pass A.

DOCUMENTATION
After each chunk, call document_learning_insights with a short title, a concise notes_markdown summary, and any metadata counters. 
Do not hand‑write paths; the tool persists to the session export directory automatically.
"""

THERAPY_PASS_B_FILE = r"""
ROLE: Persist the cleaned chunk to CSV, SQLite, and Graph‑JSON.

PRECONDITION
- `df_clean` exists in memory from Pass A (same Python session)
- Variables set: PATIENT_ID, SESSION_TYPE, SESSION_DATE, CHUNK_SIZE
- Current chunk index `k` (start at 1 per session)

FILE TARGETS (tool‑managed)
- CSV:   /workspace/exports/{PATIENT_ID}/{SESSION_TYPE}/{SESSION_DATE}/qa_chunk_{k}.csv
- SQLite: /workspace/exports/therapy.db  (table: qa_pairs; create if missing)
- Graph: /workspace/exports/{PATIENT_ID}/{SESSION_TYPE}/{SESSION_DATE}/graph_chunk_{k}.json

ACTION STEPS
1) Prepare CSV:
   - If `df_clean` is available, produce:
     - `csv_text = df_clean.to_csv(index=False)`
     - `columns = list(df_clean.columns)` (expected: ["session_date","session_type","turn_id","speaker","text_raw","text_clean"])
     - `rows = len(df_clean)`
   - Call: `write_csv_for_chunk(k, csv_text, rows, columns)`

2) Prepare Graph‑JSON object (minimal, schema‑aligned):
   - Build a Python dict `graph_dict` with:
     - "utterances": list of utterance dicts derived from `df_clean` rows, with conservative annotations
     - You may omit or leave uncertain fields as empty/Unknown; the tool will autofill top‑level fields
   - Call: `write_graph_for_chunk(k, graph_dict)`
   - The tool normalizes, validates against `graph_schema.json`, and persists.

3) SQLite upserts:
   - Open /workspace/exports/therapy.db, ensure table `qa_pairs` with PK (patient_id, session_date, session_type, turn_id)
   - UPSERT rows from `df_clean` (idempotent)

VALIDATION / LOGGING
- After each tool call, print the returned paths and counts.
- After SQLite upsert, print {"csv_rows": rows, "sqlite_upserts": upsert_count, "graph_utterances": n_utterances}.
- Do NOT write files directly; ALWAYS use the tools for CSV and Graph‑JSON.

DOCUMENTATION
- After each chunk, call `document_learning_insights(title, notes_markdown, metadata)` with a concise summary.
"""

THERAPY_PASS_C_GRAPH = r"""
ROLE: Convert Graph‑JSON chunks into Cypher for Memgraph. Do not execute; just generate files.

INPUTS
Graph‑JSON files under `/workspace/exports/{PATIENT_ID}/{SESSION_TYPE}/{SESSION_DATE}/graph_chunk_{k}.json`

NODE & RELATIONSHIP MODEL (minimal viable)
(:Persona {id: PATIENT_ID})
(:Session {date: SESSION_DATE, type: SESSION_TYPE})
(:Utterance {turn_id, speaker, text})
(:Distortion {type})
(:Emotion {label})
(:Sentiment {valence, arousal})
(:Stage {name})
(:AttachmentStyle {style})
(:Trait {name, score})
(:Schema {name})
(:DefenseMechanism {type})


LINKS
(:Persona)-[:ATTENDS]->(:Session)
(:Session)-[:INCLUDES]->(:Utterance)
(:Utterance)-[:HAS_DISTORTION]->(:Distortion)
(:Utterance)-[:TRIGGERS_EMOTION]->(:Emotion)
(:Utterance)-[:HAS_SENTIMENT]->(:Sentiment)
(:Utterance)-[:REFLECTS_STAGE]->(:Stage)
(:Persona)-[:HAS_ATTACHMENT]->(:AttachmentStyle)
(:Persona)-[:HAS_TRAIT]->(:Trait)
(:Utterance)-[:REFLECTS_SCHEMA]->(:Schema)
(:Utterance)-[:SHOWS_DEFENSE]->(:DefenseMechanism)

CYPHER GENERATION RULES
- Batch by chunk: write to `/workspace/exports/cypher/{PATIENT_ID}/{SESSION_TYPE}/{SESSION_DATE}/chunk_{k}.cypher`

WRITE
- After generating Cypher, call `write_cypher_for_chunk` with `{"k": k, "cypher_text": cypher_string}`.
- The tool writes to: `/workspace/exports/{PATIENT_ID}/{SESSION_TYPE}/{SESSION_DATE}/cypher/chunk_{k}.cypher`

DOCUMENTATION
After each chunk, call document_learning_insights with a short title, a concise notes_markdown summary, and any metadata counters. 
Do not hand‑write paths; the tool persists to the session export directory automatically.

FINAL
- When all chunks processed, emit <code>final_answer("PASS_COMPLETE")</code>.

"""

THERAPY_TASK_PROMPT = r"""
You are in chat mode with agentic capabilities. When the user types "Begin":
1) Ask which PASS to run: A (CLEAN), B (FILE), or C (GRAPH). Default: A.
2) Ask for INPUT file path (default: /workspace/data/patient_raw_data/therapy.md) and basics (PATIENT_ID, SESSION_DATE).
3) Run in chunks (CHUNK_SIZE=50 unless user overrides). After each chunk, print a one‑line status.
4) Keep Thought/Code/Observation cadence. Only call <code>final_answer("PASS_COMPLETE")</code> when the selected pass is fully done.
"""


DB_SYSTEM_PROMPT = r""" RESERVED FOR DEBUGGING"""