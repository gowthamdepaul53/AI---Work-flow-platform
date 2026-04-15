"""
planner_agent.py
----------------
Decomposes a high-level user request into an ordered list of sub-tasks,
then dispatches each to the appropriate downstream agent via n8n routing
or direct Python calls.

Prompt strategy: few-shot + chain-of-thought
"""

import json
import logging
from typing import Optional

from agents.base_agent import BaseAgent, AgentResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a task-planning AI. Your job is to break down a user request
into a precise, ordered list of atomic sub-tasks that other specialized agents can execute.

Rules:
1. Each sub-task must be independently executable.
2. Identify which agent handles each step: [summarizer | responder | rag | human].
3. Output ONLY valid JSON — no prose, no markdown fences.

Output format:
{
  "plan_id": "<unique id>",
  "steps": [
    {"step": 1, "task": "<description>", "agent": "<agent_name>", "depends_on": []},
    {"step": 2, "task": "<description>", "agent": "<agent_name>", "depends_on": [1]}
  ]
}

--- FEW-SHOT EXAMPLES ---

User: "Summarize this support ticket and send a polite reply."
Output:
{
  "plan_id": "plan_001",
  "steps": [
    {"step": 1, "task": "Retrieve relevant past tickets via RAG", "agent": "rag", "depends_on": []},
    {"step": 2, "task": "Summarize the ticket content", "agent": "summarizer", "depends_on": [1]},
    {"step": 3, "task": "Generate a polite customer reply", "agent": "responder", "depends_on": [2]}
  ]
}

User: "Flag any anomalies in today's transaction logs."
Output:
{
  "plan_id": "plan_002",
  "steps": [
    {"step": 1, "task": "Retrieve transaction log embeddings", "agent": "rag", "depends_on": []},
    {"step": 2, "task": "Summarize anomaly patterns found", "agent": "summarizer", "depends_on": [1]},
    {"step": 3, "task": "Draft anomaly report for ops team", "agent": "responder", "depends_on": [2]},
    {"step": 4, "task": "Route report for human review", "agent": "human", "depends_on": [3]}
  ]
}
"""


class PlannerAgent(BaseAgent):
    """
    Breaks a user request into an executable multi-step plan.

    Interview note:
      - Uses few-shot prompting to enforce JSON output structure.
      - Chain-of-thought is implicit — the model is guided to reason
        about dependencies between steps before assigning agents.
    """

    def __init__(self):
        super().__init__(
            agent_name="PlannerAgent",
            model="gpt-4",
            temperature=0.1,   # Low temp → more deterministic plans
            require_hitl=False,
        )

    def _run_logic(self, task: str, context: dict) -> AgentResult:
        user_prompt = f"""
User request: {task}

Context (if any): {json.dumps(context, indent=2) if context else 'None'}

Produce the plan JSON now.
"""
        raw_output, tokens = self._chat(SYSTEM_PROMPT, user_prompt)

        # Parse and validate
        try:
            plan = json.loads(raw_output)
        except json.JSONDecodeError:
            logger.warning("PlannerAgent: LLM returned non-JSON, attempting extraction.")
            # Fallback: try to extract JSON block
            import re
            match = re.search(r"\{.*\}", raw_output, re.DOTALL)
            plan = json.loads(match.group()) if match else {"steps": [], "raw": raw_output}

        logger.info(f"[PlannerAgent] Plan created: {len(plan.get('steps', []))} steps")

        return AgentResult(
            output=json.dumps(plan, indent=2),
            agent_name=self.agent_name,
            tokens_used=tokens,
            metadata={"plan": plan, "original_task": task},
        )

    def get_plan(self, task: str, context: Optional[dict] = None) -> dict:
        """Convenience method — returns the parsed plan dict directly."""
        result = self.run(task, context)
        return json.loads(result.output)
