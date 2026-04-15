"""
content_filter.py
-----------------
Blocks harmful, toxic, or policy-violating content from LLM outputs
before they reach customers.

Layers:
  1. Keyword blocklist (fast, zero-latency)
  2. Regex pattern matching (PII, profanity)
  3. OpenAI Moderation API (when enabled)
"""

import os
import re
import logging

import requests

logger = logging.getLogger(__name__)

# --- Blocklists ---
PROFANITY_PATTERNS = [
    r"\b(f+u+c+k+|sh[i1]t|b[i1]tch|a+s+s+h+o+l+e)\b",
]

PII_PATTERNS = {
    "credit_card": r"\b(?:\d[ -]?){13,16}\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    "phone": r"\b(\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
}

HARMFUL_KEYWORDS = [
    "self-harm", "suicide instructions", "bomb making",
    "how to hack", "exploit vulnerability",
]


class ContentFilter:
    """
    Multi-layer content moderation for LLM outputs.

    Returns:
        {"blocked": bool, "reason": str | None, "pii_found": list}
    """

    def __init__(self, use_openai_moderation: bool = True):
        self.use_openai_moderation = use_openai_moderation
        self.openai_api_key = os.getenv("OPENAI_API_KEY")

    def check(self, text: str) -> dict:
        text_lower = text.lower()

        # Layer 1: Harmful keyword check
        for keyword in HARMFUL_KEYWORDS:
            if keyword in text_lower:
                return {"blocked": True, "reason": f"Harmful content: '{keyword}'", "pii_found": []}

        # Layer 2: Profanity
        for pattern in PROFANITY_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return {"blocked": True, "reason": "Profanity detected", "pii_found": []}

        # Layer 3: PII detection (redact but don't block)
        pii_found = []
        for pii_type, pattern in PII_PATTERNS.items():
            if re.search(pattern, text):
                pii_found.append(pii_type)
                logger.warning(f"[ContentFilter] PII detected in output: {pii_type}")

        if pii_found:
            # Flag but don't block — PII should be redacted upstream
            return {"blocked": False, "reason": f"PII detected: {pii_found}", "pii_found": pii_found}

        # Layer 4: OpenAI Moderation API
        if self.use_openai_moderation and self.openai_api_key:
            mod_result = self._openai_moderation(text)
            if mod_result["flagged"]:
                return {
                    "blocked": True,
                    "reason": f"OpenAI Moderation: {mod_result['categories']}",
                    "pii_found": pii_found,
                }

        return {"blocked": False, "reason": None, "pii_found": pii_found}

    def _openai_moderation(self, text: str) -> dict:
        """Call OpenAI's free moderation endpoint."""
        try:
            resp = requests.post(
                "https://api.openai.com/v1/moderations",
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={"input": text[:4000]},
                timeout=5,
            )
            result = resp.json()["results"][0]
            flagged_cats = [k for k, v in result.get("categories", {}).items() if v]
            return {"flagged": result["flagged"], "categories": flagged_cats}
        except Exception as e:
            logger.warning(f"[ContentFilter] OpenAI moderation API error: {e}")
            return {"flagged": False, "categories": []}

    def redact_pii(self, text: str) -> str:
        """Replace PII with redaction tokens — safe for logging/storage."""
        redacted = text
        replacements = {
            "credit_card": "[CARD-REDACTED]",
            "ssn": "[SSN-REDACTED]",
            "email": "[EMAIL-REDACTED]",
            "phone": "[PHONE-REDACTED]",
        }
        for pii_type, pattern in PII_PATTERNS.items():
            redacted = re.sub(pattern, replacements[pii_type], redacted)
        return redacted
