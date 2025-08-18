# Custom Inference Server Explained
To run gpt-oss in its native MXFP4 quantization is basically impossible on consumer grade hardware unless one is extremely determined.
This is due to MXFP4 adding 70% additional RAM requirements (for 'reasons'), Blackwell architecture and the fact that the model unable to be unified across memory.
Aside from that, its basically just 4-bit precision.
With the help of Claude, I was able to detangle this having wasted 3 days trying endless different inference servers, puzzled as to why it wasn't working.

Therefore we have a new directory added called '/gpt-oss-service/' (though you can use any model you prefer by changing the model name in the Dockerfile).

### What this docker does (thanks Claude!):

### 1. Memory Optimization:

- Uses proper 4-bit NF4 quantization (not the problematic MXFP4)
- Should run comfortably on consumer grade hardware with ~14-16GB unified RAM usage (this might be slow if you're limited on VRAM)
- Implements memory management with offloading for larger contexts

### 2. Security & Isolation:

- Runs in its own container with GPU access
- No root privileges required
- Clean API interface that doesn't expose model internals

### 3. OpenAI Compatibility:

- Drop-in replacement for OpenAI API calls (Ollama, vLLM etc)
- Works seamlessly with your existing smolagents code
- Standard /v1/chat/completions endpoint

### 4. Integration 
- Replaces vLLM: The custom Transformers API is more reliable than vLLM for this model
- Integrate with smolagents: The client code provides a clean interface
- Supports the 'Security-driven architecture': Runs in isolation, no elevated privileges needed

### 5. Performance Optimizations
The solution includes several optimizations:

- Memory allocation: Caps GPU usage at 22GB, leaves '10%' headroom on the GPU so will adapt based on hardware.
- Quantization: Uses efficient NF4 + double quantization
- Caching: Proper model caching to avoid re-downloads
- Generation settings: Optimized for quality and speed

## Deployment
- Make sure you have your 'Hugging Face token' set.
- If you haven't used HF before, this is free and you can get one here: https://huggingface.co/settings/tokens
- Set the following environment variable:
`export HF_TOKEN="your_hf_token_here"`
- Your directory structure should be:
```
PROJECT_DIR/
├─ gpt-oss-service/
│  ├─ models/
│  │  ├─ gpt-oss-20b-4bit/
│  │  │  ├─ model.safetensors etc ... (Exactly as the model repo is formatted!)
│  │  ├─ gpt-oss-120b-4bit/
│  │  │  ├─ model.safetensors etc... (Exactly as the model repo is formatted!)
│  ├─ gpt_oss_api.py
│  ├─ Dockerfile.gpt-oss.yml
│  ├─ docker-compose.gpt-oss.yml
│  ├─ config.yml

```

### Start the service
docker-compose -f docker-compose.gpt-oss.yml up -d

### Monitor startup (initial model download takes time)
docker logs -f gpt-oss-api

### Test the service
curl http://localhost:8000/health

### Stop the service
`docker-compose -f docker-compose.gpt-oss.yml down` or just `docker compose down` if in same directory still.

### Considerations:
I'm still testing the context_window, typically OpenAI recommends 16k, but I'll confirm once tested fully.
- The context window is set in 'config.yml':
```aiignore

generation:
  max_new_tokens: 2048
  max_input_length: 6144      # Context window - THIS IS THE SETTING
  temperature: 0.7
  top_p: 0.9
```

### Persistent Docker Volumes:
- The current setup will take a little while on first boot, since its loading gpt-oss:20b and gpt-oss:120b.
- This loads the local model directory I have in my project, with the two models, and retains them (note that's around 80GB so be aware of the storage requirements).
- The benefit is that it won't need to download the models again on subsequent boots.
- If you want to clear the volume, you can do so by running:
`docker volume rm gpt-oss-service_gpt-oss-models`

## Prompt Template:
This setup uses the same architecture for the model as 'Unsloth', which can be found [here](https://docs.unsloth.ai/basics/gpt-oss-how-to-run-and-fine-tune)

and then the [fixes](https://docs.unsloth.ai/basics/gpt-oss-how-to-run-and-fine-tune#unsloth-fixes-for-gpt-oss) for the MXFP4 to NFP4 conversion:

```aiignore

# Build and start
docker-compose -f docker-compose.gpt-oss.yml up --build

# Test health (wait for model loading)
curl http://localhost:8000/health

# Test inference
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-oss-20b", 
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 100
  }'
```


## Credits
- Claude for the amazing work with the implementation.
- [Unsloth](https://docs.unsloth.ai/) for the guidance on the MXFP4 to NFP4 conversion.