"""
main.py
-------
FastAPI application entrypoint.
Wires up routes, middleware (auth, CORS, OTel tracing), and health checks.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_fastapi_instrumentator import Instrumentator

from api.routers import workflow, health, rag

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# OpenTelemetry Setup
# ------------------------------------------------------------------

def setup_telemetry():
    resource = Resource.create({"service.name": "ai-workflow-platform"})
    provider = TracerProvider(resource=resource)

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
    exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    logger.info(f"[OTel] Tracing initialized → {otlp_endpoint}")


# ------------------------------------------------------------------
# App Lifecycle
# ------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI Workflow Platform...")
    setup_telemetry()
    yield
    logger.info("Shutting down...")


# ------------------------------------------------------------------
# FastAPI App
# ------------------------------------------------------------------

app = FastAPI(
    title="AI Workflow Orchestration Platform",
    description="""
Multi-agent AI platform with n8n orchestration, RAG, and LLM agents.

**Agents**: Planner → Summarizer → Responder  
**Stack**: GPT-4 + HuggingFace + ChromaDB + PostgreSQL  
**Infra**: Docker + Kubernetes (GCP/AWS) + ArgoCD
    """,
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics at /metrics
Instrumentator().instrument(app).expose(app)

# OTel auto-instrumentation
FastAPIInstrumentor.instrument_app(app)

# Routers
app.include_router(health.router, prefix="/health", tags=["Health"])
app.include_router(workflow.router, prefix="/api/v1/workflow", tags=["Workflow"])
app.include_router(rag.router, prefix="/api/v1/rag", tags=["RAG"])


@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": "AI Workflow Orchestration Platform",
        "version": "1.0.0",
        "docs": "/docs",
        "metrics": "/metrics",
        "health": "/health",
    }
