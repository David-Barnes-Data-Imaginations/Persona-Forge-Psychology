#!/usr/bin/env python3
"""
Optimized GPT-OSS API Server with 4-bit quantization
Provides OpenAI-compatible endpoints for smolagents integration
"""

import os
import asyncio
import logging
import yaml
from typing import Dict, List, Optional, Union
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn
import json
import time
import gc

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load configuration
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Dict[str, str]]
    max_tokens: Optional[int] = 1024
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.9
    stream: Optional[bool] = False
    stop: Optional[Union[str, List[str]]] = None


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Dict]
    usage: Dict[str, int]


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    gpu_memory_used: Optional[float] = None
    gpu_memory_total: Optional[float] = None


class GPTOSSManager:
    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.device = None
        self.model_loaded = False

    async def load_model(self):
        """Load the GPT-OSS model with optimized 4-bit quantization"""
        try:
            logger.info("Starting model loading process...")

            # Check GPU availability
            if not torch.cuda.is_available():
                raise RuntimeError("CUDA not available")

            self.device = torch.device("cuda:0")
            logger.info(f"Using device: {self.device}")

            # Model configuration
            model_id = config['model']['name']
            cache_dir = config['model']['cache_dir']

            logger.info(f"Loading model: {model_id}")

            # Load tokenizer first
            self.tokenizer = AutoTokenizer.from_pretrained(
                model_id,
                cache_dir=cache_dir,
                use_fast=True,
                trust_remote_code=True
            )

            # Set pad token if not exists
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token

            # Configure 4-bit quantization
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_storage=torch.uint8
            )

            # Calculate memory allocation
            total_gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
            max_gpu_memory = min(22, total_gpu_memory * 0.9)  # Leave some headroom

            logger.info(f"Total GPU memory: {total_gpu_memory:.2f}GB")
            logger.info(f"Allocated GPU memory: {max_gpu_memory:.2f}GB")

            # Load model with optimized settings
            self.model = AutoModelForCausalLM.from_pretrained(
                model_id,
                quantization_config=bnb_config,
                device_map="auto",
                max_memory={0: f"{max_gpu_memory}GiB", "cpu": "100GiB"},
                torch_dtype=torch.float16,
                low_cpu_mem_usage=True,
                trust_remote_code=True,
                cache_dir=cache_dir,
                offload_folder="/tmp/offload"
            )

            # Set to evaluation mode
            self.model.eval()

            # Clear cache
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                gc.collect()

            self.model_loaded = True
            logger.info("Model loaded successfully!")

            # Log memory usage
            if torch.cuda.is_available():
                memory_used = torch.cuda.memory_allocated(0) / 1024 ** 3
                logger.info(f"GPU memory used: {memory_used:.2f}GB")

        except Exception as e:
            logger.error(f"Error loading model: {str(e)}")
            self.model_loaded = False
            raise

    def get_gpu_stats(self) -> Dict[str, float]:
        """Get current GPU memory statistics"""
        if not torch.cuda.is_available():
            return {}

        return {
            "memory_used": torch.cuda.memory_allocated(0) / 1024 ** 3,
            "memory_total": torch.cuda.get_device_properties(0).total_memory / 1024 ** 3,
            "memory_cached": torch.cuda.memory_reserved(0) / 1024 ** 3
        }

    async def generate_response(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """Generate response using the loaded model"""
        if not self.model_loaded:
            raise HTTPException(status_code=503, detail="Model not loaded")

        try:
            # Format messages for the model
            formatted_prompt = self._format_messages(messages)

            # Tokenize input
            inputs = self.tokenizer(
                formatted_prompt,
                return_tensors="pt",
                truncation=True,
                max_length=config['generation']['max_input_length']
            ).to(self.device)

            # Generation parameters
            gen_kwargs = {
                "max_new_tokens": kwargs.get('max_tokens', config['generation']['max_new_tokens']),
                "temperature": kwargs.get('temperature', config['generation']['temperature']),
                "top_p": kwargs.get('top_p', config['generation']['top_p']),
                "do_sample": True,
                "pad_token_id": self.tokenizer.eos_token_id,
                "eos_token_id": self.tokenizer.eos_token_id,
                "repetition_penalty": 1.1,
                "no_repeat_ngram_size": 3
            }

            # Generate response
            with torch.no_grad():
                outputs = self.model.generate(
                    inputs.input_ids,
                    attention_mask=inputs.attention_mask,
                    **gen_kwargs
                )

            # Decode response
            generated_text = self.tokenizer.decode(
                outputs[0][inputs.input_ids.shape[1]:],
                skip_special_tokens=True
            ).strip()

            return generated_text

        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Generation error: {str(e)}")

    def _format_messages(self, messages: List[Dict[str, str]]) -> str:
        """Format messages for the model"""
        formatted = ""
        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')

            if role == 'system':
                formatted += f"System: {content}\n\n"
            elif role == 'user':
                formatted += f"User: {content}\n\n"
            elif role == 'assistant':
                formatted += f"Assistant: {content}\n\n"

        formatted += "Assistant: "
        return formatted


# Initialize the manager
gpt_manager = GPTOSSManager()

# FastAPI app
app = FastAPI(title="GPT-OSS API", version="1.0.0")


@app.on_event("startup")
async def startup_event():
    """Load model on startup"""
    logger.info("Starting GPT-OSS API server...")
    await gpt_manager.load_model()


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    gpu_stats = gpt_manager.get_gpu_stats()
    return HealthResponse(
        status="healthy" if gpt_manager.model_loaded else "unhealthy",
        model_loaded=gpt_manager.model_loaded,
        gpu_memory_used=gpu_stats.get("memory_used"),
        gpu_memory_total=gpu_stats.get("memory_total")
    )


@app.post("/v1/chat/completions")
async def create_chat_completion(request: ChatCompletionRequest):
    """OpenAI-compatible chat completions endpoint"""
    try:
        # Generate response
        response_text = await gpt_manager.generate_response(
            request.messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p
        )

        # Create response
        response = ChatCompletionResponse(
            id=f"chatcmpl-{int(time.time())}",
            created=int(time.time()),
            model=request.model,
            choices=[{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response_text
                },
                "finish_reason": "stop"
            }],
            usage={
                "prompt_tokens": len(gpt_manager.tokenizer.encode(" ".join([m["content"] for m in request.messages]))),
                "completion_tokens": len(gpt_manager.tokenizer.encode(response_text)),
                "total_tokens": len(
                    gpt_manager.tokenizer.encode(" ".join([m["content"] for m in request.messages]))) + len(
                    gpt_manager.tokenizer.encode(response_text))
            }
        )

        return response

    except Exception as e:
        logger.error(f"Error in chat completion: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/models")
async def list_models():
    """List available models"""
    return {
        "object": "list",
        "data": [{
            "id": config['model']['name'],
            "object": "model",
            "created": int(time.time()),
            "owned_by": "local"
        }]
    }


if __name__ == "__main__":
    # Run the server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        access_log=True
    )