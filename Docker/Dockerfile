# Dockerfile
FROM python:3.13-slim

# System deps (build essentials for some pip wheels; git if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    tini \
 && rm -rf /var/lib/apt/lists/*

# Create non-root user (optional but recommended)
ARG USER=appuser
ARG UID=1000
ARG GID=1000
RUN groupadd -g ${GID} ${USER} && \
    useradd -m -u ${UID} -g ${GID} -s /bin/bash ${USER}

WORKDIR /app

# Copy requirements first for better layer caching
COPY ../requirements.txt /app/requirements.txt

# Create and populate virtualenv (project uses virtualenv explicitly)
ENV VENV=/app/.venv
RUN python -m venv ${VENV} && \
    . ${VENV}/bin/activate && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# Ensure our venv is the default Python in PATH
ENV PATH="${VENV}/bin:${PATH}"
ENV PYTHONUNBUFFERED=1

# Copy the rest of the code
COPY ../pyproject.toml /app/pyproject.toml
COPY ../main.py /app/main.py
COPY ../src /app/src
COPY ../tools /app/tools

# Create data/work dirs and embeddings dir
RUN mkdir -p /app/data /app/work /app/embeddings /app/states && chown -R ${USER}:${USER} /app

USER ${USER}

# Expose ports for Gradio and Ollama
EXPOSE 7860 11434

# Use tini as init for signal handling
ENTRYPOINT ["/usr/bin/tini", "--"]

# Default command: start your Python entrypoint
CMD ["python", "main.py"]