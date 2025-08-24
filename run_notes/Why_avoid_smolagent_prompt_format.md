# On newer models avoid filling out the complete smolagents prompt with big templates:
## GPT:
### Why avoid update_facts_pre_messages

- Smolagents will inject update_* on every planner cycle. With modern strong models and your router driving Pass A/B/C.
- This tends to create redundant reminders and sometimes derails the Thought/Code/Observation cadence. 
- The cleanest behavior is:
  - System prompt: rules + cadence + when to call tools + “log once per chunk.”
  - Planning.initial_facts: one‑time concrete sandbox paths, DB path, chunk size, etc.
  - No other planning injections: fewer moving parts = more deterministic runs.

If _you do_ want a per‑chunk header later (without spam)

Prefer code over planning hooks:
The router (or your chunk loop) can prepend a tiny, deterministic “chunk header” line to the task content just before calling agent.run(...) on each chunk:
`e.g., f"[RUNFACTS] chunk={k} csv_template=... graph_template=..."`

This gives you surgical control and won’t trigger extra planner cycles.
```aiignore

from src.utils.prompts import (
    THERAPY_SYSTEM_PROMPT,
    THERAPY_PASS_A_CLEAN,
    THERAPY_PASS_B_FILE,
    THERAPY_PASS_C_GRAPH,
    PLANNING_INITIAL_FACTS,
    DB_SYSTEM_PROMPT,
)

prompt_templates = {
    # Global rules + cadence + DOCUMENTATION section with “only once per chunk”
    "system_prompt": THERAPY_SYSTEM_PROMPT,

    # One-shot environment facts (paths, db, chunk size). Nothing else.
    "planning": {
        "initial_facts": PLANNING_INITIAL_FACTS,
        "initial_plan": "",
        "update_facts_pre_messages": "",
        "update_facts_post_messages": "",
        "update_plan_pre_messages": "",
        "update_plan_post_messages": "",
    },

    # You can leave this empty and let your router set the pass-specific task,
    # or put a benign default here. The router will supply A/B/C prompts.
    "managed_agent": {
        "task": "",
        "report": ""
    },

    "final_answer": {
        "pre_messages": "",
        "post_messages": ""
    }
}


```