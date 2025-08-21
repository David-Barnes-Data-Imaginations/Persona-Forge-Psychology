
# 1) Frameworks metadata (markdown) — concise, model-friendly, with anchors for retrieval
frameworks_md = textwrap.dedent(f"""
# Psychology Frameworks — Minimal Metadata
_Last updated: {datetime.date.today().isoformat()}_

## Overview
Use these definitions to normalize outputs in **THERAPY_PASS_B_FILE** and to build nodes/edges in **THERAPY_PASS_C_GRAPH**.

---

## 1. Cognitive Distortions (CBT)
**Tag:** `Distortion`  
**Clinical value:** High  
**Canonical set (short names):**
- Overgeneralization
- Catastrophizing
- Black-and-White (Dichotomous) Thinking
- Mind Reading
- Fortune Telling
- Emotional Reasoning
- Should Statements
- Personalization
- Mental Filter
- Discounting the Positive
- Labeling

**Example mapping:**
```json
{{
  "utterance": "I always mess things up.",
  "distortion": "Overgeneralization"
}}

Graph:
(:Utterance)-[:HAS_DISTORTION]->(:Distortion {{type}})
(:Distortion {{type}})-[:CAN_REPHRASE_USING]->(:Strategy {{method}})

2. Erikson Psychosocial Stages

Tag: EriksonStage
Clinical value: Moderate–High
Stages (name only):

Trust vs Mistrust
Autonomy vs Shame/Doubt

Initiative vs Guilt

Industry vs Inferiority

Identity vs Role Confusion

Intimacy vs Isolation

Generativity vs Stagnation

Integrity vs Despair

Graph:
(:Persona)-[:IN_LIFE_STAGE]->(:EriksonStage {{name}})
(:Utterance)-[:REFLECTS_STAGE]->(:EriksonStage {{name}})

3. Sentiment2D (Valence–Arousal)

Tag: Sentiment
Range: valence ∈ [-1,1], arousal ∈ [-1,1]
Graph:
(:Utterance)-[:HAS_SENTIMENT]->(:Sentiment {{valence, arousal}})
(:Sentiment)-[:CORRELATED_WITH]->(:Distortion)

4. Attachment Styles

Tag: AttachmentStyle
Allowed values: Secure, Anxious, Avoidant, Disorganized
Graph:
(:Persona)-[:HAS_ATTACHMENT]->(:AttachmentStyle {{style}})
(:Utterance)-[:INDICATES]->(:AttachmentStyle {{style}})

5. Big Five (OCEAN)

Tag: Trait
Score range: [0,1] or [0,100] (prefer [0,1])
Graph:
(:Persona)-[:HAS_TRAIT]->(:Trait {{name, score}})

6. Schema Therapy (Core Beliefs)

Tag: Schema (e.g., Abandonment, Defectiveness)
Graph:
(:Persona)-[:HAS_SCHEMA]->(:Schema {{name}})
(:Utterance)-[:REFLECTS_SCHEMA]->(:Schema {{name}})

7. Psychodynamic Markers

Tags: DefenseMechanism, Transference
Graph:
(:Utterance)-[:SHOWS_DEFENSE]->(:DefenseMechanism {{type}})
(:Utterance)-[:INDICATES]->(:Transference {{target}})

Minimal Fusion Example
Always show details
(:Utterance)-[:HAS_DISTORTION]->(:Distortion {{type:"Overgeneralization"}})
(:Utterance)-[:TRIGGERS_EMOTION]->(:Emotion {{label:"Shame"}})
(:Utterance)-[:REFLECTS_STAGE]->(:EriksonStage {{name:"Identity vs Role Confusion"}})
(:Utterance)-[:HAS_SENTIMENT]->(:Sentiment {{valence:-0.7, arousal:0.6}})




open(os.path.join(base, "graph_schema.json"), "w", encoding="utf-8").write(json.dumps(graph_schema, indent=2))

3) Minimal runtime facts YAML (for your PLANNING_INITIAL_FACTS)

facts_yaml = {
"paths": {
"export_root": "./export",
"sqlite_db": "./export/therapy.db",
"qa_csv_template": "./export/{PATIENT_ID}/{SESSION_TYPE}/{SESSION_DATE}/qa_chunk_{k}.csv",
"graph_json_template": "./export/{PATIENT_ID}/{SESSION_TYPE}/{SESSION_DATE}/graph_chunk_{k}.json",
"metadata_file": "./psych_metadata/psych_frameworks.md",
"graph_schema": "./psych_metadata/graph_schema.json"
},
"defaults": {
"patient_id": "Client_345",
"session_type": "therapy",
"session_date": datetime.date.today().isoformat(),
"chunk_size": 40
}
}
open(os.path.join(base, "planning_initial_facts.yaml"), "w", encoding="utf-8").write(yaml.safe_dump(facts_yaml, sort_keys=False))

4) Tiny validator script users can import in tools or agent code

validator_py = textwrap.dedent("""
from future import annotations
import json, jsonschema, os

def validate_graph_json(path: str, schema_path: str) -> tuple[bool, str]:
with open(schema_path, 'r', encoding='utf-8') as f:
schema = json.load(f)
with open(path, 'r', encoding='utf-8') as f:
data = json.load(f)
try:
jsonschema.validate(instance=data, schema=schema)
return True, "ok"
except jsonschema.ValidationError as e:
return False, f"validation_error: {e.message} @ {list(e.path)}"

if name == "main":
import sys
if len(sys.argv) != 3:
print("Usage: python validate_graph.py <graph_json> <schema_json>")
raise SystemExit(2)
ok, msg = validate_graph_json(sys.argv[1], sys.argv[2])
print("VALID" if ok else f"INVALID: {msg}")
""").strip()

open(os.path.join(base, "validate_graph.py"), "w", encoding="utf-8").write(validator_py)

List created files

os.listdir(base)

Always show details
Result
['psych_frameworks.md',
 'graph_schema.json',
 'planning_initial_facts.yaml',
 'validate_graph.py']

Love this idea. A tiny, model‑friendly metadata pack gives GPT‑oss a “guard‑rail recall” so Phase‑B output stays tidy and Phase‑C graphing stays consistent—even if the model wakes up a bit fuzzy. I’ve gone ahead and built you a drop‑in set:

psych_frameworks.md — concise definitions + allowed values + canonical node/edge patterns.

graph_schema.json — strict JSON Schema for your Graph‑JSON chunks (what Phase‑B should write for Phase‑C).

planning_initial_facts.yaml — the “facts only” file your Planning step can read (paths, defaults).

validate_graph.py — tiny validator you (or the agent/tool) can call before ingesting a chunk.

You can grab them here:

psych_frameworks.md

graph_schema.json

planning_initial_facts.yaml

validate_graph.py

How to wire this in (minimal changes)

Put the files in your repo
Suggested location: ./psych_metadata/ (the files are already authored with that path).

Point your embedder at the frameworks file
At startup, call your MetadataEmbedder on ./psych_metadata/psych_frameworks.md (in addition to any dataset metadata). That gives the agent a crisp retrieval target when it asks “what’s a valid distortion tag again?”

Use the YAML in Planning
Replace your verbose planning facts with a simple RAG + file read of planning_initial_facts.yaml. It already includes:

paths:
  export_root: ./export
  sqlite_db: ./export/therapy.db
  qa_csv_template: ./export/{PATIENT_ID}/{SESSION_TYPE}/{SESSION_DATE}/qa_chunk_{k}.csv
  graph_json_template: ./export/{PATIENT_ID}/{SESSION_TYPE}/{SESSION_DATE}/graph_chunk_{k}.json
  metadata_file: ./psych_metadata/psych_frameworks.md
  graph_schema: ./psych_metadata/graph_schema.json
defaults:
  patient_id: Client_345
  session_type: therapy
  session_date: <today>
  chunk_size: 40


Tighten THERAPY_PASS_B_FILE
Keep your three FILE TARGETS (CSV / SQLite / Graph‑JSON), then add two musts:

“Before saving Graph‑JSON, validate using validate_graph.py and graph_schema.json; on failure, fix & re‑emit.”

“For any psychological tag, normalize against the contents of psych_frameworks.md (e.g., ‘Overgeneralisation’ → ‘Overgeneralization’).”

SQLite tooling (quick reminder)
You’re good to add sqlite3 and sqlalchemy to additional_authorized_imports. Also keep the “CreateSQLiteDB” tool we discussed as a fallback that:

ensures ./export/therapy.db exists,

creates table qa_pairs(q TEXT, a TEXT, patient_id TEXT, session_type TEXT, session_date TEXT, utterance_id TEXT, meta JSON) if missing,

upserts by (patient_id, session_type, session_date, utterance_id).

Keep or trim?

The Fusion Example section you pasted is useful to keep (short!)—models benefit from a single, concrete pattern showing multi‑framework tagging on one utterance.

The Graph Architecture block is also worth keeping, but condensed (the md I gave already encodes node/edge forms, so you can remove anything redundant).

Tiny code hooks (agent side)

Normalize & validate before write (pseudo):

# normalize distortion/stage names against psych_frameworks.md (retrieved via MetadataEmbedder)
# then:
ok, msg = validate_graph_json(out_path, "./psych_metadata/graph_schema.json")
if not ok:
    # repair & revalidate; only then write final file / upsert SQLite


Planning facts ingestion:

import yaml, json
facts = yaml.safe_load(open("./psych_metadata/planning_initial_facts.yaml"))
