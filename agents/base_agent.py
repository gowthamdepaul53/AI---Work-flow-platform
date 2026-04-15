"""
base_agent.py
-------------
Shared base class for all agents in the multi-agent system.
Handles LangChain LLM setup, OpenTelemetry tracing, token tracking,
and the human-in-the-loop approval gate.
"""

import os
import time
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from agents.bias_checker import BiasChecker
from agents.content_filter import ContentFilter

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class AgentResult:
    """Structured result returned by every agent."""

    def __init__(
        self,
        output: str,
        agent_name: str,
        tokens_used: int = 0,
        flagged: bool = False,
        flag_reason: Optional[str] = None,
        metadata: Optional[dict] = None,
    ):
        self.output = output
        self.agent_name = agent_name
        self.tokens_used = tokens_used
        self.flagged = flagged
        self.flag_reason = flag_reason
        self.metadata = metadata or {}
        self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "output": self.output,
            "agent_name": self.agent_name,
            "tokens_used": self.tokens_used,
            "flagged": self.flagged,
            "flag_reason": self.flag_reason,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


class BaseAgent(ABC):
    """
    Abstract base for all LLM agents.

    Subclasses implement `_run_logic()` and get:
      - LangChain ChatOpenAI wired up automatically
      - OTel spans around every invocation
      - Bias + content filtering on every output
      - Human-in-the-loop gate for sensitive tasks
    """

    SENSITIVE_KEYWORDS = {"legal", "medical", "financial", "private", "confidential"}

    def __init__(
        self,
        agent_name: str,
        model: str = "gpt-4",
        temperature: float = 0.2,
        require_hitl: bool = False,
    ):
        self.agent_name = agent_name
        self.require_hitl = require_hitl
        self.bias_checker = BiasChecker()
        self.content_filter = ContentFilter()

        self.llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
        )
        logger.info(f"[{self.agent_name}] Initialized with model={model}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, task: str, context: Optional[dict] = None) -> AgentResult:
        """
        Entry point. Wraps _run_logic with tracing, filtering, and HITL.
        """
        with tracer.start_as_current_span(f"{self.agent_name}.run") as span:
            span.set_attribute("agent.name", self.agent_name)
            span.set_attribute("task.length", len(task))

            try:
                start = time.perf_counter()
                result = self._run_logic(task, context or {})
                elapsed = time.perf_counter() - start

                span.set_attribute("agent.tokens_used", result.tokens_used)
                span.set_attribute("agent.latency_ms", round(elapsed * 1000, 2))

                # --- Responsible AI checks ---
                result = self._apply_responsible_ai(result)

                # --- Human-in-the-loop gate ---
                if self.require_hitl or self._is_sensitive(task):
                    result = self._hitl_gate(result)

                span.set_status(Status(StatusCode.OK))
                return result

            except Exception as exc:
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                logger.error(f"[{self.agent_name}] Error: {exc}", exc_info=True)
                raise

    # ------------------------------------------------------------------
    # Subclass contract
    # ------------------------------------------------------------------

    @abstractmethod
    def _run_logic(self, task: str, context: dict) -> AgentResult:
        """Core agent logic — must be implemented by each subclass."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _chat(self, system_prompt: str, user_prompt: str) -> tuple[str, int]:
        """Call the LLM and return (text, tokens_used)."""
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response = self.llm.invoke(messages)
        tokens = response.response_metadata.get("token_usage", {}).get("total_tokens", 0)
        return response.content, tokens

    def _apply_responsible_ai(self, result: AgentResult) -> AgentResult:
        """Run bias check and content filter on the output."""
        bias_report = self.bias_checker.check(result.output)
        if bias_report["flagged"]:
            result.flagged = True
            result.flag_reason = f"Bias detected: {bias_report['reason']}"
            logger.warning(f"[{self.agent_name}] Bias flag: {bias_report['reason']}")

        filter_report = self.content_filter.check(result.output)
        if filter_report["blocked"]:
            result.flagged = True
            result.flag_reason = f"Content blocked: {filter_report['reason']}"
            result.output = "[REDACTED — content policy violation]"
            logger.warning(f"[{self.agent_name}] Content blocked.")

        return result

    def _is_sensitive(self, task: str) -> bool:
        return any(kw in task.lower() for kw in self.SENSITIVE_KEYWORDS)

    def _hitl_gate(self, result: AgentResult) -> AgentResult:
        """
        Human-in-the-loop: in production this pushes to an approval queue.
        For demo, it logs and marks the result as pending review.
        """
        if result.flagged:
            logger.info(
                f"[{self.agent_name}] HITL: output flagged — "
                f"routing to human review queue. Reason: {result.flag_reason}"
            )
            result.metadata["hitl_status"] = "pending_review"
        else:
            result.metadata["hitl_status"] = "auto_approved"
        return result
