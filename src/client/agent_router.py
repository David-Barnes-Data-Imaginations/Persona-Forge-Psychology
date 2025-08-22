from src.client.agent import CustomAgent
from src.utils.prompts import THERAPY_SYSTEM_PROMPT, THERAPY_PASS_A_CLEAN, THERAPY_PASS_B_FILE, THERAPY_PASS_C_GRAPH
from src.utils.config import (
CHUNK_SIZE,
PATIENT_ID,
SESSION_DATE,
SESSION_TYPE,
)

class TherapyRouter:
    def __init__(self, agent: CustomAgent):
        self.agent = agent

    def _compose_task(self, system_prompt: str, pass_prompt: str, overrides: dict) -> str:

        # small wrapper that lets you pass run-time vars inline
        kv = "\n".join([f"{k}={v!r}" for k, v in overrides.items()])
        return f"{system_prompt}\n\n{pass_prompt}\n\n# RUNTIME\n{kv}"

    def run_pass(self, pass_name: str, *,
                 patient_id: str = PATIENT_ID,
                 session_type: str = SESSION_TYPE,
                 session_date: str = SESSION_DATE,
                 chunk_size: int = CHUNK_SIZE,
                 input_path: str = "./therapy.md"):

        overrides = dict(
            PATIENT_ID=patient_id,
            SESSION_TYPE=session_type,
            SESSION_DATE=session_date,
            CHUNK_SIZE=chunk_size,
            INPUT_PATH=input_path,
        )
        if pass_name.upper() == "A":
            task = self._compose_task(THERAPY_SYSTEM_PROMPT, THERAPY_PASS_A_CLEAN, overrides)
        elif pass_name.upper() == "B":
            task = self._compose_task(THERAPY_SYSTEM_PROMPT, THERAPY_PASS_B_FILE, overrides)
        elif pass_name.upper() == "C":
            task = self._compose_task(THERAPY_SYSTEM_PROMPT, THERAPY_PASS_C_GRAPH, overrides)
        else:
            return "Unknown pass. Use A, B, or C."

        return self.agent.handle_agentic_mode(task, stream=False)

    def run_full_pipeline(self, **kwargs):
        outA = self.run_pass("A", **kwargs)
        outB = self.run_pass("B", **kwargs)
        outC = self.run_pass("C", **kwargs)
        return "\n\n".join([str(outA), str(outB), str(outC)])
