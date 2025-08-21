This directory structure is just here because I use 'https://ascii-tree-generator.com/' to create my directory tree visually every now and then once I start to lose track of all the files. Obviously you could just get AI to do it, but that defeats the purpose for me.
Since it takes ages at this point I just add it to git incase its useful for anyone.
```aiignore
PROJECT_DIR/
├─ tools/
│  ├─ __init__.py
│  ├─ documentation_tools.py
│  ├─ help_tools.py
│  ├─ sql_tools.py
src/
├─ data/
│  ├─ psych_metadata/
│  │  ├─ graph_schema.json
│  │  ├─ validate_graph.py
│  │  ├─ planning_initial_facts.yaml
│  │  ├─ psych_frameworks.md
│  ├─ patient_raw_data/
│  │  ├─ therapy.md
├─ client/
│  ├─ __init__.py
│  ├─ agent.py
│  ├─ agent_router.py
│  ├─ telemetry.py
│  ├─ requirements.agent.txt
│  ├─ ui/
│  │  ├─ sentiment_suite/
│  │  │    ├─ data/
│  │  │    ├─ models/
│  │  │    ├─ circumplex_plot.py
│  │  │    ├─ distortion_detection.py
│  │  │    ├─ emotion_mapping.py
│  │  │    ├─ enhanced_visualisation.py
│  │  │    ├─ sentiment_dashboard_tabs.py
│  │  │    ├─ SentimentSuite.py (main)
│  │  ├─ chat.py
├─ states/
│  ├─ shared_state.py
│  ├─ agent_step_log.jsonl # outdated
│  ├─ paths.py
│  ├─ persistence.py
│  ├─ __init__.py
├─ __init__.py
├─ utils/
│  ├─ config.py
│  ├─ file_reader.py
│  ├─ io_helpers.py
│  ├─ ollama_utils
│  ├─ prompts.py
│  ├─ metadata_embedder.py
│  ├─ sqlite_helpers.py
│  ├─ __init__.py
main.py
README.md
requirements.txt
insights/
embeddings/
```