# tools/csv_tools.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from smolagents import Tool
import pandas as pd

from src.utils.export_writer import ExportWriter
from src.utils import config as C

REQUIRED_COLUMNS = [
    "session_date", "session_type", "turn_id", "speaker", "text_raw", "text_clean"
]

class WriteCSVForChunk(Tool):
    """
    Persist a cleaned QA chunk as CSV under the session export tree.
    Accepts either CSV text or a list of row dicts (records). Validates required columns.
    """
    name = "write_csv_for_chunk"
    description = (
        "Write a CSV for chunk k to the session export directory. "
        "Either provide `csv_text` or `records` (list of objects)."
    )
    inputs = {
        "k": {"type": "integer", "description": "Chunk index.", "required": True},
        "csv_text": {
            "type": "string",
            "description": "Raw CSV text to save. Mutually exclusive with `records`.",
            "default": None,
            "nullable": True
        },
        "records": {
            "type": "array",
            "description": "List of row dicts to form a DataFrame. Mutually exclusive with `csv_text`.",
            "items": {"type": "object"},
            "default": None,
            "nullable": True
        },
        "columns": {
            "type": "array",
            "description": "Optional explicit column order (applied if `records` provided).",
            "items": {"type": "string"},
            "default": None,
            "nullable": True
        },
    }
    output_type = "object"

    def __init__(self, sandbox=None):
        super().__init__()
        self.sandbox = sandbox

    def _validate_columns(self, df: pd.DataFrame) -> list[str]:
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        return missing

    def forward(
        self,
        k: int,
        csv_text: Optional[str] = None,
        records: Optional[List[Dict[str, Any]]] = None,
        columns: Optional[List[str]] = None,
    ):
        if (csv_text is None and records is None) or (csv_text and records):
            return {
                "ok": False,
                "error": "Provide exactly one of `csv_text` or `records`.",
            }

        if records is not None:
            try:
                df = pd.DataFrame.from_records(records)
                # optional column order
                if columns:
                    # add any missing as empty if caller specified order that includes them
                    for c in columns:
                        if c not in df.columns:
                            df[c] = None
                    df = df[columns]
            except Exception as e:
                return {"ok": False, "error": f"failed_to_build_dataframe: {e}"}
        else:
            # csv_text path
            try:
                from io import StringIO
                df = pd.read_csv(StringIO(csv_text))
            except Exception as e:
                return {"ok": False, "error": f"failed_to_parse_csv_text: {e}"}

        # Validate required columns for Pass B contract
        missing = self._validate_columns(df)
        if missing:
            return {"ok": False, "error": f"missing_required_columns: {missing}"}

        # Persist via ExportWriter
        exporter = ExportWriter(
            sandbox=self.sandbox,
            patient_id=C.PATIENT_ID,
            session_type=C.SESSION_TYPE,
            session_date=C.SESSION_DATE,
        )
        paths = exporter.write_csv(k, df)
        return {"ok": True, "paths": paths, "rows": int(df.shape[0]), "chunk_id": k}
