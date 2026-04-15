"""
summarizer_agent.py
-------------------
Summarizes support tickets and documents using a Hugging Face BART model
(local or via HF Inference API), with GPT-4 fallback for long inputs.

Demonstrates: Hugging Face integration, contextual prompting, token budget mgmt.
"""

import os
import logging
from typing import Optional

import requests
from agents.base_agent import BaseAgent, AgentResult

logger = logging.getLogger(__name__)

# Contextual prompt template — few-shot style
SUMMARY_SYSTEM_PROMPT = """You are a concise summarization assistant for a customer support platform.
Your summaries are used by agents to quickly understand issues without reading full documents.

Rules:
- Keep summaries under 150 words.
- Always extract: (1) core issue, (2) urgency level [LOW/MEDIUM/HIGH/CRITICAL], (3) suggested next step.
- Use bullet points for clarity.

--- EXAMPLE ---
Input: "Hi, I've been waiting 3 weeks for my refund and nobody is responding to my emails.
        My order #4521 was cancelled on 12/1. This is completely unacceptable."

Summary:
• Issue: Refund not received 3 weeks after order #4521 cancellation (12/1).
• Urgency: HIGH — customer frustrated, no prior response.
• Next Step: Escalate to billing team; send acknowledgment email within 2 hours.
"""


class SummarizerAgent(BaseAgent):
    """
    Dual-mode summarizer:
      - Short docs (< 512 tokens): Hugging Face BART via Inference API
      - Long docs / complex tickets: GPT-4 via LangChain fallback

    Interview note:
      - HF Inference API avoids hosting costs for the HF model
      - BART is fine-tuned for abstractive summarization (CNN/DailyMail)
      - We switch to GPT-4 when HF output quality is insufficient
    """

    HF_MODEL = "facebook/bart-large-cnn"
    HF_API_URL = f"https://api-inference.huggingface.co/models/{HF_MODEL}"
    MAX_HF_CHARS = 1500  # Approx 512 tokens

    def __init__(self):
        super().__init__(
            agent_name="SummarizerAgent",
            model="gpt-4",
            temperature=0.3,
        )
        self.hf_token = os.getenv("HF_TOKEN")

    def _run_logic(self, task: str, context: dict) -> AgentResult:
        document = context.get("document", task)
        doc_type = context.get("doc_type", "ticket")  # ticket | document | log

        # Route: HF for short, GPT-4 for long
        if len(document) <= self.MAX_HF_CHARS and self.hf_token:
            summary, tokens, model_used = self._hf_summarize(document)
        else:
            summary, tokens, model_used = self._gpt4_summarize(document, doc_type)

        logger.info(f"[SummarizerAgent] Used {model_used}, {tokens} tokens")

        return AgentResult(
            output=summary,
            agent_name=self.agent_name,
            tokens_used=tokens,
            metadata={
                "model_used": model_used,
                "doc_type": doc_type,
                "input_length": len(document),
            },
        )

    def _hf_summarize(self, text: str) -> tuple[str, int, str]:
        """Call Hugging Face Inference API."""
        headers = {"Authorization": f"Bearer {self.hf_token}"}
        payload = {
            "inputs": text,
            "parameters": {"max_length": 150, "min_length": 40, "do_sample": False},
        }

        try:
            resp = requests.post(self.HF_API_URL, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            result = resp.json()
            summary = result[0]["summary_text"] if isinstance(result, list) else str(result)
            # HF doesn't return token counts — estimate from chars
            estimated_tokens = len(text.split()) + len(summary.split())
            return summary, estimated_tokens, "hf-bart-large-cnn"

        except Exception as exc:
            logger.warning(f"[SummarizerAgent] HF API failed ({exc}), falling back to GPT-4")
            return self._gpt4_summarize(text, "ticket")

    def _gpt4_summarize(self, text: str, doc_type: str) -> tuple[str, int, str]:
        """Summarize via GPT-4 with contextual prompt."""
        user_prompt = f"""
Document type: {doc_type}

Content to summarize:
\"\"\"
{text[:6000]}  # Respect context window
\"\"\"

Provide the summary now.
"""
        summary, tokens = self._chat(SUMMARY_SYSTEM_PROMPT, user_prompt)
        return summary, tokens, "gpt-4"

    def batch_summarize(self, documents: list[dict]) -> list[AgentResult]:
        """Summarize multiple documents — used in bulk processing workflows."""
        return [
            self.run(
                task=doc.get("text", ""),
                context={"document": doc.get("text", ""), "doc_type": doc.get("type", "ticket")},
            )
            for doc in documents
        ]
