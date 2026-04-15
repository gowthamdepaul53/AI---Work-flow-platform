"""
routers/rag.py — RAG query and document indexing endpoints
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from agents.rag_engine import RAGEngine

router = APIRouter()
rag_engine = RAGEngine()


class QueryRequest(BaseModel):
    question: str
    filter_metadata: Optional[dict] = None


class IndexRequest(BaseModel):
    documents: List[dict]  # [{"id": str, "text": str, "metadata": dict}]


@router.post("/query")
async def query_knowledge_base(request: QueryRequest):
    """Semantic search + RAG answer generation."""
    try:
        result = rag_engine.query(request.question, request.filter_metadata)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/index")
async def index_documents(request: IndexRequest):
    """Add documents to the vector store."""
    try:
        count = rag_engine.add_documents(request.documents)
        return {"indexed": count, "status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
async def similarity_search(q: str, top_k: int = 5):
    """Raw similarity search — no generation."""
    results = rag_engine.similarity_search(q, top_k)
    return {"results": results, "count": len(results)}
