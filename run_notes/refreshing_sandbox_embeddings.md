Metadata embeddings can be refreshed dependant on how the run goes.
Leave them in to simulate 'agentic learning' or refresh them to have the model start without any of its notes and insights.
In production this would be left on and intermittently inspected.

Run in CLI with `python src/utils/metadata_embedder.py --dirs ./src/data/psych_metadata ./src/data/patient_raw_data`

Or force a refresh with `python src/utils/metadata_embedder.py --refresh`
