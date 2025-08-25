Absolutely—here’s a drop‑in “Pattern B” version of your WriteCypherForChunk that mirrors the working approach you used for WriteGraphForChunk:
```
class WriteCypherForChunk(Tool):
    """
    Persist Cypher text for chunk k under the session `cypher/` directory.
    """
    name = "write_cypher_for_chunk"
    description = "Write Cypher text for chunk k to the session's cypher directory."

    # Keep schema permissive (nullable True) to satisfy smolagents; enforce in code.
    inputs = {
        "k": {
            "type": "integer",
            "description": "Chunk index.",
            "nullable": True
        },
        "cypher_text": {
            "type": "string",
            "description": "Cypher statements to write.",
            "nullable": True
        },
    }
    output_type = "object"

    def __init__(self, sandbox=None):
        # Probe before super().__init__ triggers validation (handy while iterating)
        try:
            from pprint import pformat
            print("[W CYC] inputs right now ->", pformat(self.inputs))
        except Exception:
            pass
        super().__init__()
        self.sandbox = sandbox

    def forward(self, k: Optional[int], cypher_text: Optional[str]):
        # Hard enforcement so the tool behaves like a required API.
        if k is None:
            return {"ok": False, "error": "missing_required_argument: k"}
        if cypher_text is None:
            return {"ok": False, "error": "missing_required_argument: cypher_text"}

        text = cypher_text.strip()
        if not text:
            return {"ok": False, "error": "empty_cypher_text"}

        t = session_templates(C.PATIENT_ID, C.SESSION_TYPE, C.SESSION_DATE)
        fname = f"cypher/chunk_{k}.cypher"

        exporter = ExportWriter(
            sandbox=self.sandbox,
            patient_id=C.PATIENT_ID,
            session_type=C.SESSION_TYPE,
            session_date=C.SESSION_DATE,
        )
        # Ensure trailing newline for POSIX-y niceness
        payload = text if text.endswith("\n") else text + "\n"
        paths = exporter.write_text(k, fname, payload)

        preview = "\n".join(text.splitlines()[:15])
        return {"ok": True, "paths": paths, "preview": preview, "chunk_id": k}
```

Why this works with smolagents:

- Schema uses nullable: True to appease the validator.
- The forward(...) signature uses Optional[...] and then enforces requireds at runtime (same pattern as your working WriteGraphForChunk).
- Kept behavior identical otherwise, with a small guard for empty text and a trailing newline nicety.
- If the agent was previously sending k or cypher_text as null (or omitting), this will now return a clear error string instead of exploding at init time.
  - Tip: if you change this file and still see the old error, nuke bytecode and re‑run to avoid stale imports:

```
find . -name "__pycache__" -type d -exec rm -rf {} + ; \
find . -name "*.pyc" -delete
```


Then sanity‑check what’s actually imported:
```
python -c "import tools.graph_tools as g, inspect, json; \
print(inspect.getsource(g.WriteCypherForChunk)); \
print('\\nSCHEMA:', json.dumps(g.WriteCypherForChunk.inputs, indent=2))"
```

