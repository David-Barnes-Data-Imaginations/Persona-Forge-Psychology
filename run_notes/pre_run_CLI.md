# use this primarily as the main one includes the therapy.md
python -m src.utils.metadata_embedder --refresh --verbose --dirs ./src/data/psych_metadata

# or multiple dirs
python -m src.utils.metadata_embedder --refresh --verbose --dirs ./src/data/psych_metadata ./src/data/patient_raw_data


# show resolved defaults from the updated CLI
python -m src.utils.metadata_embedder

# force a rebuild
python -m src.utils.metadata_embedder --refresh

# embed a specific dir only
python -m src.utils.metadata_embedder --dirs ./src/data/psych_metadata

# or verbose/refresh options:

# from repo root
python -m src.utils.metadata_embedder --refresh --verbose ./src/data/psych_metadata
python -m src.utils.metadata_embedder --refresh --verbose --dirs ./src/data/psych_metadata
python -m src.utils.metadata_embedder --refresh --verbose --dirs ./src/data/psych_metadata ./src/data/patient_raw_data

# Session path notes:
- make_session_paths() will create:
    - /workspace/exports/{PATIENT_ID}/{SESSION_TYPE}/{SESSION_DATE}
    - And ensure the per-chunk file targets like qa_chunk_1.csv / graph_chunk_1.json have a valid parent directory.

- Your tools (write_graph_for_chunk, write_cypher_for_chunk, write_qa_to_sqlite) already use session_templates and ExportWriter, so once the base exists, they’ll write to the correct sandbox paths. SQLite will be /workspace/exports/therapy.db as intended.

Quick sanity check you can run
- CLI facts preview (no side effects):
    - uv run python -m src.main pass A --print_facts

- Ensure the sandbox export base exists (with your env):
    - uv run python -m src.main pass A --patient_id "Client_345" --session_type "therapy_text" --session_date "2025-08-19" --print_facts
    - Then run a Pass B after Pass A to see CSV/Graph writes.
