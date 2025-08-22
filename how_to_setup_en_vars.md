Here's how to set them up to run, obviously these aren't real keys but for the purpose of demonstration:
---
# App → vLLM
MODEL_ID=gpt-oss-20b

# OpenAI (used by MetadataEmbedder + agent notes embeddings)
OPENAI_API_FAKE_KEY="sk-proj-abcdef123456"
E2B_API_FAKE_KEY="e2b_abcdef123456"
USE_E2B=true
USE_HOST_OLLAMA=true
OLLAMA_HOST=localhost
USE_OLLAMA_EMBEDDINGS=false

# Obligatory Langfuse
LANGFUSE_PUBLIC_FAKE_KEY="pk-lf-abcdef123456"
LANGFUSE_SECRET_FAKE_KEY="sk-lf-abcdef123456"

# HF x 2 for testing (these are for smolagents parsingm only 1 required)
HF_API_FAKE_TOKEN="hf_abcdef123456"
HF_FAKE_TOKEN="hf_abcdef123456"

# Config vars set in code:
PATIENT_ID="Client_345" (or as provided)
SESSION_TYPE="therapy_text"
SESSION_DATE="2025-08-19" # use provided date or a passed‑in value
CHUNK_SIZE=50
---