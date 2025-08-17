"""
GPT-OSS Client for Smolagents integration
Provides a clean interface to the dockerized GPT-OSS API (which runs HF Transformers)
"""

import os
import requests
import logging
from typing import Dict, List, Optional, Union
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class GPTOSSConfig:
    base_url: str = "http://localhost:8000"
    model_name: str = "openai/gpt-oss-20b"
    timeout: int = 120
    max_retries: int = 3


class GPTOSSClient:
    """Client for communicating with the dockerized GPT-OSS API"""

    def __init__(self, config: Optional[GPTOSSConfig] = None):
        self.config = config or GPTOSSConfig()
        self.session = requests.Session()
        self.session.timeout = self.config.timeout

        # Override with environment variables if available
        if os.getenv("GPT_OSS_BASE_URL"):
            self.config.base_url = os.getenv("GPT_OSS_BASE_URL")

    def is_healthy(self) -> bool:
        """Check if the GPT-OSS service is healthy and model is loaded"""
        try:
            response = self.session.get(f"{self.config.base_url}/health")
            response.raise_for_status()
            health_data = response.json()
            return health_data.get("model_loaded", False)
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def wait_for_service(self, max_wait: int = 300) -> bool:
        """Wait for the service to become healthy"""
        import time
        start_time = time.time()

        while time.time() - start_time < max_wait:
            if self.is_healthy():
                logger.info("GPT-OSS service is ready!")
                return True

            logger.info("Waiting for GPT-OSS service to become ready...")
            time.sleep(10)

        logger.error(f"GPT-OSS service not ready after {max_wait} seconds")
        return False

    def chat_completion(
            self,
            messages: List[Dict[str, str]],
            max_tokens: int = 1024,
            temperature: float = 0.7,
            top_p: float = 0.9,
            **kwargs
    ) -> str:
        """Generate a chat completion using GPT-OSS"""
        try:
            payload = {
                "model": self.config.model_name,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
                **kwargs
            }

            response = self.session.post(
                f"{self.config.base_url}/v1/chat/completions",
                json=payload
            )
            response.raise_for_status()

            data = response.json()
            return data["choices"][0]["message"]["content"]

        except Exception as e:
            logger.error(f"Chat completion failed: {e}")
            raise

    def get_models(self) -> List[str]:
        """Get list of available models"""
        try:
            response = self.session.get(f"{self.config.base_url}/v1/models")
            response.raise_for_status()
            data = response.json()
            return [model["id"] for model in data["data"]]
        except Exception as e:
            logger.error(f"Failed to get models: {e}")
            return []


# src/agents/gpt_oss_agent.py
"""
Enhanced agent that uses GPT-OSS for specific tasks
"""

from smolagents import CodeAgent, Tool
from typing import Dict, List, Any
from .gpt_oss_client import GPTOSSClient, GPTOSSConfig


class GPTOSSAgent(CodeAgent):
    """
    Enhanced CodeAgent that can use GPT-OSS for specialized tasks
    """

    def __init__(self, tools: List[Tool], **kwargs):
        super().__init__(tools=tools, **kwargs)

        # Initialize GPT-OSS client
        self.gpt_oss_client = GPTOSSClient(
            GPTOSSConfig(
                base_url=kwargs.get("gpt_oss_url", "http://localhost:8000"),
                model_name=kwargs.get("gpt_oss_model", "openai/gpt-oss-20b")
            )
        )

        # Wait for service on initialization
        if not self.gpt_oss_client.wait_for_service():
            raise RuntimeError("GPT-OSS service not available")

    async def use_gpt_oss_for_task(
            self,
            task_description: str,
            context: Dict[str, Any] = None,
            temperature: float = 0.7
    ) -> str:
        """
        Use GPT-OSS for specific tasks that benefit from its capabilities

        Args:
            task_description: The task to perform
            context: Additional context for the task
            temperature: Sampling temperature

        Returns:
            Generated response from GPT-OSS
        """

        # Build messages for GPT-OSS
        messages = [
            {
                "role": "system",
                "content": "You are a helpful AI assistant specialized in code analysis, "
                           "data processing, and complex reasoning tasks. Provide clear, "
                           "accurate, and well-structured responses."
            }
        ]

        # Add context if provided
        if context:
            context_str = "\n".join([f"{k}: {v}" for k, v in context.items()])
            messages.append({
                "role": "user",
                "content": f"Context:\n{context_str}\n\nTask: {task_description}"
            })
        else:
            messages.append({
                "role": "user",
                "content": task_description
            })

        # Generate response
        try:
            response = self.gpt_oss_client.chat_completion(
                messages=messages,
                temperature=temperature,
                max_tokens=8000 # will tune later
            )
            return response
        except Exception as e:
            self.logger.error(f"GPT-OSS task failed: {e}")
            # Fallback to regular agent behavior
            return await self.run(task_description)


# Integration with existing main.py
def create_gpt_oss_enhanced_agent(tools: List[Tool]) -> GPTOSSAgent:
    """
    Factory function to create a GPT-OSS enhanced agent
    """
    return GPTOSSAgent(
        tools=tools,
        gpt_oss_url=os.getenv("GPT_OSS_BASE_URL", "http://localhost:8000"),
        gpt_oss_model="openai/gpt-oss-20b"
    )


# Example usage in your smolagents framework
async def example_gpt_oss_usage():
    """Example of how to use GPT-OSS for specific tasks"""

    # Create tools (your existing tools)
    tools = []  # Your tool list here

    # Create enhanced agent
    agent = create_gpt_oss_enhanced_agent(tools)

    # Use GPT-OSS for complex reasoning
    analysis_result = await agent.use_gpt_oss_for_task(
        task_description="Analyze this code for potential security vulnerabilities",
        context={
            "code": "def process_user_input(user_data): exec(user_data)",
            "language": "python",
            "context": "web application"
        },
        temperature=0.3  # Lower temperature for analysis tasks
    )

    print(f"Security analysis: {analysis_result}")

    # Use regular agent for other tasks
    regular_result = await agent.run("Generate a simple data visualization")
    print(f"Regular task result: {regular_result}")