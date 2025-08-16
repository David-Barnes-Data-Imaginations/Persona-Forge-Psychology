services:
  triton:
    image: nvcr.io/nvidia/tritonserver:24.05-py3
    container_name: triton
    restart: unless-stopped
    ports:
      - "8005:8000"  # gRPC
      - "8006:8001"  # HTTP
      - "8007:8002"  # Metrics
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
    volumes:
      - ./models:/models
      - ./config:/config
    command: >
      tritonserver --model-repository=/models --log-verbose=1
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]
    runtime: nvidia