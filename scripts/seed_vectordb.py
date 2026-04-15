"""
seed_vectordb.py
----------------
Loads sample support documents and tickets into ChromaDB for demo/interview.
Run: python scripts/seed_vectordb.py

In production, this would consume from an S3 bucket, PostgreSQL, or Confluence API.
"""

import sys
import os
import uuid
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from agents.rag_engine import RAGEngine

logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sample Knowledge Base — Support Articles
# ---------------------------------------------------------------------------
KNOWLEDGE_BASE = [
    {
        "id": "kb-001",
        "text": """Refund Policy: Customers are eligible for a full refund within 30 days of purchase.
        After 30 days, partial refunds may be issued at the discretion of the support team.
        Refunds are processed within 5-7 business days to the original payment method.
        For orders cancelled before shipment, refunds process within 1-2 business days.
        Contact billing@platform.com for expedited refund requests.""",
        "metadata": {"type": "policy", "category": "billing", "version": "2025-01"},
    },
    {
        "id": "kb-002",
        "text": """API Rate Limiting: The platform enforces rate limits to ensure fair usage.
        Free tier: 100 requests/minute. Pro tier: 1000 requests/minute. Enterprise: unlimited.
        When rate limited, the API returns HTTP 429 with a Retry-After header.
        To increase limits, upgrade your plan or contact support for enterprise pricing.
        Rate limits reset every 60 seconds on a rolling window basis.""",
        "metadata": {"type": "technical", "category": "api", "version": "2025-01"},
    },
    {
        "id": "kb-003",
        "text": """Account Password Reset: To reset your password, click 'Forgot Password' on the
        login page and enter your registered email address. You will receive a reset link within
        5 minutes. The link expires after 24 hours. If you don't receive the email, check your
        spam folder or contact support. For SSO users, password reset is handled by your
        identity provider (Google, Okta, Azure AD).""",
        "metadata": {"type": "faq", "category": "account", "version": "2025-01"},
    },
    {
        "id": "kb-004",
        "text": """Subscription Cancellation: You can cancel your subscription at any time from
        Account Settings > Billing > Cancel Subscription. Your access continues until the end
        of the current billing period. Data is retained for 90 days after cancellation.
        To avoid charges, cancel at least 24 hours before your renewal date.
        Enterprise contracts require 30-day written notice for cancellation.""",
        "metadata": {"type": "policy", "category": "billing", "version": "2025-01"},
    },
    {
        "id": "kb-005",
        "text": """Data Export: Users can export all their data from Account Settings > Data & Privacy
        > Export Data. Exports include: tickets, messages, account history, and usage logs.
        CSV and JSON formats are available. Large exports may take up to 2 hours to generate.
        A download link will be emailed when ready. Enterprise users have access to the
        bulk export API for automated data pipelines.""",
        "metadata": {"type": "technical", "category": "data", "version": "2025-01"},
    },
    {
        "id": "kb-006",
        "text": """Webhook Configuration: Webhooks can be configured in Settings > Integrations > Webhooks.
        Supported events: ticket.created, ticket.resolved, payment.succeeded, payment.failed.
        Webhook payloads are signed with HMAC-SHA256 using your webhook secret.
        Failed deliveries are retried up to 5 times with exponential backoff.
        Webhook logs are available for 30 days in the dashboard.""",
        "metadata": {"type": "technical", "category": "integrations", "version": "2025-01"},
    },
]

# ---------------------------------------------------------------------------
# Sample historical support tickets (for ticket similarity search)
# ---------------------------------------------------------------------------
HISTORICAL_TICKETS = [
    {
        "id": f"ticket-{uuid.uuid4().hex[:8]}",
        "text": "My refund for order #3891 hasn't arrived after 2 weeks. I need this resolved urgently.",
        "metadata": {"type": "ticket", "category": "billing", "resolved": True, "resolution_days": 2},
    },
    {
        "id": f"ticket-{uuid.uuid4().hex[:8]}",
        "text": "Getting 429 errors on the API. We're on Pro tier and shouldn't be hitting limits.",
        "metadata": {"type": "ticket", "category": "api", "resolved": True, "resolution_days": 1},
    },
    {
        "id": f"ticket-{uuid.uuid4().hex[:8]}",
        "text": "Can't log in after password reset. The link says it's expired but I just requested it.",
        "metadata": {"type": "ticket", "category": "account", "resolved": True, "resolution_days": 1},
    },
    {
        "id": f"ticket-{uuid.uuid4().hex[:8]}",
        "text": "How do I export all our ticket data for our quarterly compliance audit?",
        "metadata": {"type": "ticket", "category": "data", "resolved": True, "resolution_days": 0},
    },
]


def seed(chroma_host: str = "localhost", chroma_port: int = 8001):
    logger.info("Connecting to ChromaDB...")
    rag = RAGEngine(chroma_host=chroma_host, chroma_port=chroma_port)

    logger.info(f"Indexing {len(KNOWLEDGE_BASE)} knowledge base articles...")
    kb_count = rag.add_documents(KNOWLEDGE_BASE)
    logger.info(f"✅ Indexed {kb_count} KB articles.")

    # Use a separate collection for historical tickets
    from agents.rag_engine import RAGEngine as RE
    ticket_rag = RE(
        collection_name="historical_tickets",
        chroma_host=chroma_host,
        chroma_port=chroma_port,
    )
    logger.info(f"Indexing {len(HISTORICAL_TICKETS)} historical tickets...")
    ticket_count = ticket_rag.add_documents(HISTORICAL_TICKETS)
    logger.info(f"✅ Indexed {ticket_count} historical tickets.")

    # Quick smoke test
    logger.info("Running smoke test query...")
    result = rag.query("How long does a refund take?")
    logger.info(f"Smoke test answer: {result['answer'][:100]}...")
    logger.info(f"Sources: {[s['id'] for s in result['sources']]}")

    logger.info("🎉 Vector database seeded successfully!")


if __name__ == "__main__":
    host = os.getenv("CHROMA_HOST", "localhost")
    port = int(os.getenv("CHROMA_PORT", "8001"))
    seed(host, port)
