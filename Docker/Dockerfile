# docker/Dockerfile (app)
FROM python:3.12-slim

# system deps (no GPUs / cu* libs here)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git curl tini && \
    rm -rf /var/lib/apt/lists/*

# install uv (fast, deterministic pip replacement)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh -s -- --yes
ENV PATH="/root/.local/bin:${PATH}"

ARG USER=appuser
ARG UID=1000
ARG GID=1000
RUN groupadd -g ${GID} ${USER} && useradd -m -u ${UID} -g ${GID} -s /bin/bash ${USER}

WORKDIR /app

# copy minimal app requirements (see §2)
COPY requirements-app.txt /app/requirements-app.txt

# create venv & install
ENV VENV=/app/.venv
RUN python -m venv ${VENV} && \
    . ${VENV}/bin/activate && \
    uv pip install --upgrade pip && \
    uv pip install --no-cache -r /app/requirements-app.txt

ENV PATH="${VENV}/bin:${PATH}"
ENV PYTHONUNBUFFERED=1

# copy code
COPY pyproject.toml /app/pyproject.toml
COPY main.py /app/main.py
COPY src /app/src
COPY tools /app/tools

RUN mkdir -p /app/data /app/work /app/embeddings /app/states && \
    chown -R ${USER}:${USER} /app

USER ${USER}

EXPOSE 7860
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "main.py"]
