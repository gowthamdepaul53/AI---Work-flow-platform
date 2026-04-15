"""
responder_agent.py
------------------
Generates final customer-facing responses using GPT-4.
Receives summarized context + RAG retrieval results as grounding.

Demonstrates: contextual prompting, tone control, structured output.
"""

import logging
from agents.base_agent import BaseAgent, AgentResult

logger = logging.getLogger(__name__)

RESPONDER_SYSTEM_PROMPT = """You are a professional customer support agent for a SaaS platform.
Write empathetic, clear, and solution-focused responses.

Tone guidelines:
- Acknowledge the customer's frustration without being defensive.
- Be specific — reference the actual issue, not generic platitudes.
- End with a clear next step or resolution timeline.
- Keep responses under 200 words unless a detailed technical explanation is needed.

--- EXAMPLE ---
Issue Summary: Customer's refund (order #4521) is 3 weeks overdue.
Context: Refunds typically process in 5-7 business days. Billing team handles escalations.

Response:
Hi [Name],

Thank you for reaching out, and I sincerely apologize for the delay on your refund for order #4521.
This is not the experience we want for our customers.

I've escalated this directly to our billing team as a priority. You should receive your refund within
1–2 business days. I'll personally follow up with you by [DATE] to confirm it's been processed.

If you have any other questions in the meantime, don't hesitate to reach out.

Warm regards,
Support Team
"""


class ResponderAgent(BaseAgent):
    """
    Generates customer support responses grounded in:
      - Issue summary (from SummarizerAgent)
      - RAG context (from RAGEngine)
      - Urgency level
    """

    def __init__(self):
        super().__init__(
            agent_name="ResponderAgent",
            model="gpt-4",
            temperature=0.5,   # Slightly higher for natural language variation
            require_hitl=False,
        )

    def _run_logic(self, task: str, context: dict) -> AgentResult:
        summary = context.get("summary", task)
        rag_context = context.get("rag_context", "")
        urgency = context.get("urgency", "MEDIUM")
        customer_name = context.get("customer_name", "Valued Customer")
        ticket_id = context.get("ticket_id", "N/A")

        user_prompt = f"""
Customer: {customer_name}
Ticket ID: {ticket_id}
Urgency: {urgency}

Issue Summary:
{summary}

Additional Context from Knowledge Base:
{rag_context if rag_context else "No additional context retrieved."}

Write the customer response now.
"""

        response_text, tokens = self._chat(RESPONDER_SYSTEM_PROMPT, user_prompt)

        logger.info(
            f"[ResponderAgent] Generated response for ticket {ticket_id} "
            f"(urgency={urgency}, tokens={tokens})"
        )

        return AgentResult(
            output=response_text,
            agent_name=self.agent_name,
            tokens_used=tokens,
            metadata={
                "ticket_id": ticket_id,
                "urgency": urgency,
                "customer_name": customer_name,
            },
        )
