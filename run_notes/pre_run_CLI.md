# use this primarily as the main one includes the therapy.md
`python -m src.utils.metadata_embedder --refresh --verbose ./src/data/psych_metadata`

# show resolved defaults from the updated CLI
python -m src.utils.metadata_embedder

# force a rebuild
python -m src.utils.metadata_embedder --refresh

# embed a specific dir only
python -m src.utils.metadata_embedder --dirs ./src/data/psych_metadata

# or verbose/refresh options:

# from repo root
python -m src.utils.metadata_embedder --verbose
python -m src.utils.metadata_embedder --refresh --verbose
python -m src.utils.metadata_embedder --dirs ./src/data/psych_metadata --verbose
