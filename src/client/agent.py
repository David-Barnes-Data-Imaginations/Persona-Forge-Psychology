import datetime
import asyncio
import json
from smolagents.agent_types import AgentText
from smolagents import CodeAgent, Tool
from smolagents.models import LiteLLMModel
from typing import List, Any, AsyncGenerator, Optional
from src.utils.prompts import CA_SYSTEM_PROMPT, DB_SYSTEM_PROMPT, PLANNING_INITIAL_FACTS, PLANNING_INITIAL_PLAN, \
    PLANNING_UPDATE_FACTS_PRE, PLANNING_UPDATE_FACTS_POST, PLANNING_UPDATE_PLAN_PRE, PLANNING_UPDATE_PLAN_POST, \
    CA_MAIN_PROMPT
import litellm
import os

# Prompt templates
prompt_templates = {
    "system_prompt": CA_SYSTEM_PROMPT,
    "planning": {
        "initial_facts": PLANNING_INITIAL_FACTS,
        "initial_plan": PLANNING_INITIAL_PLAN,
        "update_facts_pre_messages": PLANNING_UPDATE_FACTS_PRE,
        "update_facts_post_messages": PLANNING_UPDATE_FACTS_POST,
        "update_plan_pre_messages": PLANNING_UPDATE_PLAN_PRE,
        "update_plan_post_messages": PLANNING_UPDATE_PLAN_POST
    },
    "managed_agent": {
        "task": CA_MAIN_PROMPT,
        "report": ""
    },
        "final_answer": {
        "pre_messages": "",
        "post_messages": ""
    }
}

debug_templates = {
    "system_prompt": DB_SYSTEM_PROMPT,
    "planning": {

    },
    "managed_agent": {
        "task": "",
        "report": ""
    },
    "final_answer": {
        "pre_messages": "",
        "post_messages": ""
    }
}
# StepController handles step management by adding a time delay, alongside the manual controls
class StepController:
    def __init__(self):
        self.ready = asyncio.Event()
        self.manual_mode = False

    def next(self):
        self.ready.set()

    async def wait(self):
        if self.manual_mode:
            await self.ready.wait()
            self.ready.clear()
        else:
            await asyncio.sleep(1.5)

    def toggle_mode(self, manual: bool):
        self.manual_mode = manual
        if not manual:
            self.ready.set()  # Unblock any pending waits

class CustomAgent:
    def __init__(
            self,
            tools: Optional[List[Tool]] = None,
            sandbox=None,
            metadata_embedder=None,
            model_id: Optional[str] = None,
            ollama_host: str = "localhost",
            python_executor=None,
    ):

        self.ollama_host = ollama_host
        raw_model = model_id or "gpt-oss:20b"

        model = LiteLLMModel(
            model_id=f"openai/{raw_model}",
            api_base=f"http://{ollama_host}:11434/v1",
            api_key="ollama",
            num_ctx=8192,
        )

        self.agent = CodeAgent(
            tools=tools,
            model=model,
            prompt_templates=prompt_templates,
            additional_authorized_imports=[
                "pandas",
                "sqlalchemy",
                "scikit-learn",
                "statistics",
                "smolagents",
                "seaborn",
                "random",
                "itertools",
                "queue",
                "math",
                "io",
                "numpy",
                "matplotlib",
                "plotly",
            ],
            add_base_tools=True,
            planning_interval=5,
            max_steps=30,
            verbosity_level=3,  # increase to see parsed code/content in logs
        )
        # Optional: set conservative defaults for code generation
        if hasattr(self.agent, "default_additional_args"):
            self.agent.default_additional_args = {"temperature": 0.2, "top_p": 0.9}

        # Optional: docker-backed executor injection
        if python_executor is not None:
            try:
                self.agent.python_executor = python_executor
                if hasattr(self.agent, "executor_type"):
                    self.agent.executor_type = "local"
            except Exception as e:
                print(f"⚠️ Failed to set custom python executor: {e}")

        # Sanity check via OpenAI-compatible route
        try:
            test_response = litellm.completion(
                model=f"openai/{raw_model}",
                messages=[{"role": "user", "content": "ping"}],
                api_base=f"http://{ollama_host}:11434/v1",
                api_key="ollama",
                stream=False,
            )
            print("✅ Ollama (OpenAI-compatible) test response:",
                  test_response['choices'][0]['message']['content'][:80], "...")
        except Exception as e:
            print("❌ Ollama OpenAI-compatible sanity check failed:", str(e))

    def handle_chat_mode(self, task: str, images=None, stream=False, reset=False, additional_args=None):
        """Handle normal chat interactions"""
        try:
            model_id = self.agent.model.model_id
            if not model_id.startswith("openai/"):
                model_id = f"openai/{model_id}"

            response = litellm.completion(
                model=model_id,
                messages=[{"role": "user", "content": task}],
                api_base=f"http://{self.ollama_host}:11434/v1",
                api_key="ollama",
                stream=stream
            )
            if stream:
                return response
            else:
                return response['choices'][0]['message']['content']
        except Exception as e:
            return f"Error in chat mode: {str(e)}"


    def handle_agentic_mode(self, task: str, images=None, stream=False, reset=False, additional_args=None):
        """Handle agentic workflow execution"""
        # Pass through to the underlying agent with proper streaming support
        if stream:
            return self.agent.run(task, stream=True)
        else:
            return self.agent.run(task)

    def start_agentic_workflow(self):
        """Start the agentic workflow. The following tools are available:"""
        self.is_agentic_mode = True
        print(self.agent.tools)
        print(self.agent.tools.values())
        return """🚀 Starting agentic workflow! I'm now in analysis mode. 


I can help you clean and analyze this data using a systematic, chunk-based approach.

I have access to the Turtle Games dataset with the following files:

- Reviews CSV: /data/turtle_reviews.csv
- Sales CSV: /data/turtle_sales.csv 

I should clean the dataset in chunks of 200 rows and use the SaveCleanedDataframe tool to save the results.
Once all chunks are cleaned, I will print the dataframe and submit "Dataframe cleaned" as my final answer.
"""


    def return_to_chat_mode(self):
        """Return to chat mode after agentic workflow completes"""
        self.is_agentic_mode = False
        return "✅ Analysis complete! I'm back in chat mode. Feel free to ask me questions about the analysis or request new tasks."

    def cleanup(self):
        """Clean up agent resources."""
        try:
            if hasattr(self.agent, 'cleanup'):
                self.agent.cleanup()
                print("✅ Agent cleanup completed")
            else:
                print("ℹ️ Agent doesn't have cleanup method")
        except Exception as e:
            print(f"⚠️ Error during agent cleanup: {e}")

    def __enter__(self):
        """Support for context manager usage."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cleanup when exiting context manager."""
        self.cleanup()

    def log_agent_step(self, thought: str, tool: str = "", params: dict = None, result: str = ""):
        event = {
            "thought": thought,
            "tool": tool,
            "params": params or {},
            "result": result
        }
        if self.telemetry:
            self.telemetry.log_agent_step(event)
        with open("states/agent_step_log.jsonl", "a") as f:
            f.write(json.dumps(event) + "\n")
        print("🧠 AGENT STEP saved to log.")
        return event

# --- Context Manager ---
class SmartContextManager:
    def __init__(self, limit_tokens=80000):
        self.history = []
        self.limit_tokens = limit_tokens

    def _approx_tokens(self, text: str) -> int:
        return int(len(text.split()) * 0.75)

    def add(self, message: str):
        self.history.append(message)
        while self._approx_tokens("\n".join(self.history)) > self.limit_tokens:
            self.history.pop(0)

    def get(self) -> str:
        return "\n".join(self.history)


    async def agent_runner(self, task: str) -> AsyncGenerator[dict[str, Any] | dict[str, str], None]:
        """Run agent with context management and return to chat mode after final_answer"""
        reasoning_preface = AgentText(text=f"Can you reason through this step by step before taking any action?\n{task}")
        self.context = SmartContextManager()
        trace = self.agent.run(reasoning_preface)
        self.controller = StepController()

        for i, step in enumerate(trace.steps):
            # Append the step prompt to context
            if hasattr(step, "message"):
                self.context.add(f"Step {i}: {step.message.content}")

            elif hasattr(step, "thought") and hasattr(step, "tool_name"):
                # Log the reasoning chain to context and store insight in RAG
                insight = f"Thought: {step.thought}\nTool: {step.tool_name}\nParams: {step.tool_input}\nObservation: {step.observation}"
                self.context.add(insight)

                # Store insight in RAG if supported
                if hasattr(self.agent, "store_insight"):
                    self.agent.store_insight(insight)

                yield {
                    "thought": step.thought,
                    "tool_name": step.tool_name,
                    "tool_input": step.tool_input,
                    "observation": step.observation
                }

            else:
                yield {
                    "step_info": str(step)
                }

            # Manual mode pause or 0.5s fallback
            await self.controller.wait(2 if self.controller.manual_mode else 2)

            # Slight breathing room after first step
            if i == 0:
                await asyncio.sleep(0.5)

        # Check if we have a final answer and signal return to chat mode
        if hasattr(trace, 'final_answer') and trace.final_answer:
            yield {
                "final_answer": str(trace.final_answer),
                "return_to_chat": True
            }

    def toggle_manual_mode(self, manual: bool):
        self.controller.toggle_mode(manual)

    def next_step(self):
        self.controller.next()

class ToolFactory:
    """Factory for creating all tools with proper dependencies"""

    def __init__(self, sandbox, metadata_embedder=None):
        self.sandbox = sandbox
        self.metadata_embedder = metadata_embedder

    def create_all_tools(self) -> List[Tool]:
        """Create all tools with sandbox and metadata_embedder dependencies injected"""

        # Import your custom tool
        from tools.documentation_tools import (DocumentLearningInsights,
                                               RetrieveMetadata, RetrieveSimilarChunks,
                                               ValidateCleaningResults)
        from tools.dataframe_storage import SaveCleanedDataframe

        

        # Create instances of your custom tools
        tools = [
            DocumentLearningInsights(sandbox=self.sandbox),
            RetrieveMetadata(sandbox=self.sandbox, metadata_embedder=self.metadata_embedder),
            RetrieveSimilarChunks(sandbox=self.sandbox),
            ValidateCleaningResults(sandbox=self.sandbox),
            SaveCleanedDataframe(sandbox=self.sandbox),
            
        ]
        return tools
