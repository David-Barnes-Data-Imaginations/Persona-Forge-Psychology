"""
Ollama server utilities for managing the local model server.
"""

import requests
import time
import subprocess
from typing import Optional, Dict, List



def check_ollama_server(host: str = "localhost", port: int = 11434, timeout: int = 5) -> bool:
    """Check if Ollama server is running"""
    try:
        response = requests.get(f"http://{host}:{port}/api/version", timeout=timeout)
        return response.status_code == 200
    except requests.RequestException:
        return False


def get_available_models(host: str = "localhost", port: int = 11434) -> List[Dict]:
    """Get list of available models from Ollama"""
    try:
        response = requests.get(f"http://{host}:{port}/api/tags")
        if response.status_code == 200:
            return response.json().get('models', [])
        return []
    except requests.RequestException:
        return []


def wait_for_ollama_server(host: str = "localhost", port: int = 11434, max_wait: int = 60) -> bool:
    """Wait for Ollama server to be ready"""
    print(f"⏳ Waiting for Ollama server at {host}:{port}...")

    start_time = time.time()
    while time.time() - start_time < max_wait:
        if check_ollama_server(host, port):
            print("✅ Ollama server is ready!")
            return True

        print("⏳ Still waiting for Ollama server...")
        time.sleep(5)

    print("❌ Ollama server failed to start within timeout")
    return False


def start_ollama_server_background() -> Optional[subprocess.Popen]:
    """Start Ollama server in background"""

    if check_ollama_server():
        print("✅ Ollama server already running")
        return None

    print(f"🚀 Starting Ollama server...")

    try:
        # Start Ollama serve command
        process = subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return process
    except Exception as e:
        print(f"❌ Failed to start Ollama server: {e}")
        return None


def pull_model(model_name: str, host: str = "localhost", port: int = 11434, timeout: int = 300) -> bool:
    """Pull a model from Ollama if not already present"""
    try:
        print(f"📥 Checking if model {model_name} is already pulled...")
        
        # Check if model exists
        response = requests.get(f"http://{host}:{port}/api/tags", timeout=10)
        if response.status_code == 200:
            models = response.json().get("models", [])
            for model in models:
                if model.get("name") == model_name:
                    print(f"✅ Model {model_name} is already pulled")
                    return True
        
        # If we get here, need to pull model
        print(f"📥 Pulling model {model_name}...")
        response = requests.post(
            f"http://{host}:{port}/api/pull",
            json={"name": model_name},
            timeout=timeout
        )
        
        if response.status_code == 200:
            print(f"✅ Successfully pulled model {model_name}")
            return True
        else:
            print(f"❌ Failed to pull model {model_name}: {response.text}")
            return False
            
    except requests.RequestException as e:
        print(f"❌ Error pulling model {model_name}: {str(e)}")
        return False


def generate_completion(
        prompt: str,
        model: str = "gpt-oss:20b",
        host: str = "localhost",
        port: int = 11434,
        stream: bool = True
) -> str:
    """Generate completion using Ollama API"""
    try:
        url = f"http://{host}:{port}/api/generate"
        data = {
            "model": model,
            "prompt": prompt,
            "stream": stream
        }

        response = requests.post(url, json=data)
        if response.status_code == 200:
            if stream:
                return response.text
            else:
                return response.json().get('response', '')
        else:
            print(f"❌ Error generating completion: {response.status_code}")
            return ""

    except Exception as e:
        print(f"❌ Error generating completion: {e}")
        return ""


def chat_completion(
        messages: List[Dict],
        model: str = "gpt-oss:20b",
        host: str = "localhost",
        port: int = 11434,
        stream: bool = False
) -> str:
    """Generate chat completion using Ollama API"""
    try:
        url = f"http://{host}:{port}/api/chat"
        data = {
            "model": model,
            "messages": messages,
            "stream": stream
        }

        response = requests.post(url, json=data)
        if response.status_code == 200:
            if stream:
                return response.text
            else:
                return response.json().get('message', {}).get('content', '')
        else:
            print(f"❌ Error generating chat completion: {response.status_code}")
            return ""

    except Exception as e:
        print(f"❌ Error generating chat completion: {e}")
    return ""
