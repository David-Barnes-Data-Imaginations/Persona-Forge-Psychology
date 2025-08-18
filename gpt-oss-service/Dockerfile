# Use a CUDA 12.x image instead of 13.0
FROM nvidia/cuda:12.3.2-devel-ubuntu22.04

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-dev \
    python3-venv \
    git \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install uv (modern Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
# Fix the PATH to include where uv is installed
ENV PATH="/root/.cargo/bin:/root/.local/bin:$PATH"

# Create working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements-gpt-oss.txt .

# Create virtual environment and install dependencies using uv
RUN uv venv /app/venv
ENV PATH="/app/venv/bin:$PATH"
ENV VIRTUAL_ENV="/app/venv"

# Install Python dependencies using uv (much faster than pip)
RUN uv pip install -r requirements-gpt-oss.txt

# Copy application files
COPY gpt_oss_api.py .
COPY config.yaml .

# Create model cache directory
RUN mkdir -p /models

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start the API server
CMD ["python3", "gpt_oss_api.py"]