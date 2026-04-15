"""
routers/workflow.py
-------------------
API routes for triggering and monitoring multi-agent workflows.
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from agents.planner_agent import PlannerAgent
from agents.summarizer_agent import SummarizerAgent
from agents.responder_agent import ResponderAgent
from agents.rag_engine import RAGEngine

logger = logging.getLogger(__name__)
router = APIRouter()

# Singleton agent instances (in prod, use dependency injection)
planner = PlannerAgent()
summarizer = SummarizerAgent()
responder = ResponderAgent()
rag_engine = RAGEngine()


# ------------------------------------------------------------------
# Request / Response Models
# ------------------------------------------------------------------

class SupportTicketRequest(BaseModel):
    ticket_id: str
    customer_name: str
    ticket_text: str
    urgency: Optional[str] = "MEDIUM"  # LOW | MEDIUM | HIGH | CRITICAL


class WorkflowResponse(BaseModel):
    ticket_id: str
    plan: dict
    summary: str
    rag_context: str
    response: str
    total_tokens: int
    flagged: bool
    hitl_status: str


class TaskRequest(BaseModel):
    task: str
    context: Optional[dict] = None


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@router.post("/support-ticket", response_model=WorkflowResponse)
async def process_support_ticket(request: SupportTicketRequest):
    """
    Full multi-agent pipeline for customer support:
    Plan → RAG → Summarize → Respond → Safety Check

    This is the main demo endpoint — shows the complete agent collaboration.
    """
    logger.info(f"Processing ticket {request.ticket_id} (urgency={request.urgency})")
    total_tokens = 0

    try:
        # Step 1: Plan
        plan = planner.get_plan(
            task=f"Handle support ticket: {request.ticket_text}",
            context={"ticket_id": request.ticket_id, "urgency": request.urgency},
        )
        total_tokens += 0  # Planner tokens tracked internally

        # Step 2: RAG — retrieve relevant past tickets / KB articles
        rag_result = rag_engine.query(request.ticket_text)
        rag_context = rag_result["answer"]
        total_tokens += rag_result["tokens_used"]

        # Step 3: Summarize the ticket
        summary_result = summarizer.run(
            task=request.ticket_text,
            context={
                "document": request.ticket_text,
                "doc_type": "ticket",
                "rag_context": rag_context,
            },
        )
        total_tokens += summary_result.tokens_used

        # Step 4: Generate response
        response_result = responder.run(
            task="Generate customer response",
            context={
                "summary": summary_result.output,
                "rag_context": rag_context,
                "urgency": request.urgency,
                "customer_name": request.customer_name,
                "ticket_id": request.ticket_id,
            },
        )
        total_tokens += response_result.tokens_used

        return WorkflowResponse(
            ticket_id=request.ticket_id,
            plan=plan,
            summary=summary_result.output,
            rag_context=rag_context,
            response=response_result.output,
            total_tokens=total_tokens,
            flagged=response_result.flagged,
            hitl_status=response_result.metadata.get("hitl_status", "unknown"),
        )

    except Exception as e:
        logger.error(f"Workflow error for ticket {request.ticket_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/plan")
async def create_plan(request: TaskRequest):
    """Generate an execution plan for any task without running it."""
    plan = planner.get_plan(request.task, request.context)
    return {"plan": plan}


@router.post("/summarize")
async def summarize_document(request: TaskRequest):
    """Summarize a document or ticket."""
    result = summarizer.run(request.task, request.context or {})
    return result.to_dict()
