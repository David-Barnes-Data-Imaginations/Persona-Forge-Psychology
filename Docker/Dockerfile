# dockerfile
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    tini \
 && rm -rf /var/lib/apt/lists/*

ARG USER=appuser
ARG UID=1000
ARG GID=1000
RUN groupadd -g ${GID} ${USER} && \
    useradd -m -u ${UID} -g ${GID} -s /bin/bash ${USER}

WORKDIR /app

# IMPORTANT: these paths must be relative to the build context (project root),
# since docker-compose sets build.context: ..
COPY ../requirements.txt /app/requirements.txt

ENV VENV=/app/.venv
RUN python -m venv ${VENV} && \
    . ${VENV}/bin/activate && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

ENV PATH="${VENV}/bin:${PATH}"
ENV PYTHONUNBUFFERED=1

# Copy the rest of the code (from build context root)
COPY pyproject.toml /app/pyproject.toml
COPY main.py /app/main.py
COPY src /app/src
COPY tools /app/tools

RUN mkdir -p /app/data /app/work /app/embeddings /app/states && chown -R ${USER}:${USER} /app

USER ${USER}

EXPOSE 7860 11434
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "main.py"]