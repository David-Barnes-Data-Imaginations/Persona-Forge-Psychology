from __future__ import annotations
import json
import sys
from jsonschema import validate as js_validate, ValidationError, SchemaError

def validate_graph_json(path: str, schema_path: str) -> tuple[bool, str]:
    """Validate a Graph‑JSON file against the schema. Returns (ok, message)."""
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
    except Exception as e:
        return False, f"failed_to_read_schema: {e}"

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return False, f"failed_to_read_graph: {e}"

    try:
        js_validate(instance=data, schema=schema)
        return True, "ok"
    except ValidationError as e:
        # e.path is a deque; cast to list for readable output
        return False, f"validation_error: {e.message} @ path {list(e.path)}"
    except SchemaError as e:
        return False, f"schema_error: {e.message}"

def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: python validate_graph.py <graph_json> <schema_json>")
        return 2
    graph_path, schema_path = argv[1], argv[2]
    ok, msg = validate_graph_json(graph_path, schema_path)
    print("VALID" if ok else f"INVALID: {msg}")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main(sys.argv))


