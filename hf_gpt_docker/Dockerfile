# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3.11-pip \
    python3.11-dev \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set Python 3.11 as default
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
RUN update-alternatives --install /usr/bin/pip3 pip3 /usr/bin/pip3.11 1

# Create working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.gpt-oss.txt .
RUN pip3 install --no-cache-dir -r requirements.gpt-oss.txt

# Copy application files
COPY gpt_oss_api.py .
COPY config.yaml .
# Do i need to copy the models in. For example `COPY /models/bnb/gpt-oss-20b/` since i also have '/models/bnb/gpt-oss-120b/' in 'models'


# Create model cache directory
RUN mkdir -p /models

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start the API server
CMD ["python3", "gpt_oss_api.py"]