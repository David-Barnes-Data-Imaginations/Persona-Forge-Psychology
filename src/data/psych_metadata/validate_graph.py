from __future__ import annotations
import json, jsonschema, os

def validate_graph_json(path: str, schema_path: str) -> tuple[bool, str]:
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = json.load(f)
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    try:
        jsonschema.validate(instance=data, schema=schema)
    return True, "ok"

    except e = jsonschema.ValidationError
            return False, f"validation_error: {e.message} @ {list(e.path)}"

if name == "main":
import sys

    if len(sys.argv) != 3:
        print("Usage: python validate_graph.py <graph_json> <schema_json>")
        raise SystemExit(2)
    ok, msg = validate_graph_json(sys.argv[1], sys.argv[2])
    print("VALID" if ok else f"INVALID: {msg}")


