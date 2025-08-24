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

