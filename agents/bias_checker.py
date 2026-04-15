"""
bias_checker.py
---------------
Responsible AI — detects potentially biased language in LLM outputs.

Approach:
  1. Lexical scan for known bias-indicative patterns
  2. Demographic parity check (protected attribute mentions)
  3. Optional: GPT-4 meta-evaluation for subtle bias (toggled by env var)

Interview note:
  This is a lightweight, explainable heuristic layer — not a replacement
  for full fairness audits. In production, pair with tools like IBM AI Fairness 360
  or Microsoft Responsible AI Toolbox for quantitative fairness metrics.
"""

import os
import re
import logging

logger = logging.getLogger(__name__)

# Protected attributes — flag if output treats groups differently
PROTECTED_ATTRIBUTES = [
    "race", "gender", "religion", "nationality", "age", "disability",
    "sexual orientation", "ethnicity", "socioeconomic",
]

# Patterns that may signal biased framing
BIAS_PATTERNS = [
    (r"\ball (men|women|blacks|whites|muslims|christians|asians)\b", "demographic generalization"),
    (r"\b(obviously|clearly|naturally)\s+(they|those people)\b", "othering language"),
    (r"\b(exotic|articulate for|surprisingly smart)\b", "microaggression indicator"),
    (r"\b(illegal alien|illegals)\b", "dehumanizing immigration language"),
    (r"\b(mankind|manpower|chairman)\b", "non-inclusive gendered language"),
]


class BiasChecker:
    """
    Lightweight bias detection for LLM outputs.

    Returns:
        {"flagged": bool, "reason": str | None, "patterns_found": list}
    """

    def __init__(self, use_llm_eval: bool = False):
        self.use_llm_eval = use_llm_eval or os.getenv("BIAS_LLM_EVAL", "false").lower() == "true"

    def check(self, text: str) -> dict:
        text_lower = text.lower()
        patterns_found = []

        # --- Lexical scan ---
        for pattern, label in BIAS_PATTERNS:
            if re.search(pattern, text_lower):
                patterns_found.append(label)
                logger.debug(f"[BiasChecker] Pattern match: {label}")

        # --- Protected attribute differential treatment ---
        attr_hits = [attr for attr in PROTECTED_ATTRIBUTES if attr in text_lower]
        if len(attr_hits) >= 2:
            # Multiple protected attributes mentioned — check for differential framing
            patterns_found.append(f"multiple protected attributes: {attr_hits}")

        if patterns_found:
            return {
                "flagged": True,
                "reason": "; ".join(patterns_found),
                "patterns_found": patterns_found,
            }

        # --- Optional LLM meta-evaluation ---
        if self.use_llm_eval:
            return self._llm_eval(text)

        return {"flagged": False, "reason": None, "patterns_found": []}

    def _llm_eval(self, text: str) -> dict:
        """
        Ask GPT-4 to evaluate the text for subtle bias.
        Only runs when BIAS_LLM_EVAL=true — adds ~$0.002/call.
        """
        from langchain_openai import ChatOpenAI
        from langchain.schema import HumanMessage, SystemMessage

        llm = ChatOpenAI(model="gpt-4", temperature=0, openai_api_key=os.getenv("OPENAI_API_KEY"))
        prompt = f"""Evaluate the following text for bias, stereotyping, or unfair framing.
Reply with JSON only: {{"biased": true/false, "reason": "..."}}

Text: {text[:1000]}"""

        try:
            import json
            resp = llm.invoke([HumanMessage(content=prompt)])
            result = json.loads(resp.content)
            return {
                "flagged": result.get("biased", False),
                "reason": result.get("reason"),
                "patterns_found": ["llm_eval"],
            }
        except Exception as e:
            logger.warning(f"[BiasChecker] LLM eval failed: {e}")
            return {"flagged": False, "reason": None, "patterns_found": []}
