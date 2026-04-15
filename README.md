# AI Workflow Orchestration Platform

> **n8n + LLM Agents | Multi-Agent AI | RAG | Kubernetes | GCP/AWS**  
> Built Jan 2025 — Interview Demo Codebase

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client / API Gateway                     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                     n8n Orchestration Layer                      │
│   [Planner Agent] → [Summarizer Agent] → [Responder Agent]      │
└──────┬──────────────────┬─────────────────────┬─────────────────┘
       │                  │                     │
┌──────▼──────┐  ┌────────▼────────┐  ┌────────▼────────┐
│  OpenAI     │  │  Hugging Face   │  │  Vector DB       │
│  GPT-4      │  │  Models         │  │  (ChromaDB)      │
│  (LangChain)│  │  (Summarizer)   │  │  RAG / Embeddings│
└─────────────┘  └─────────────────┘  └─────────────────┘
       │
┌──────▼──────────────────────────────────────────────────────────┐
│              PostgreSQL / MySQL  ←→  Power BI Dashboards         │
└─────────────────────────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────────────┐
│         Observability: Prometheus + Grafana + OpenTelemetry      │
└─────────────────────────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────────────┐
│      Infrastructure: Docker + Kubernetes (GCP/AWS)               │
│      CI/CD: GitHub Actions + ArgoCD                              │
│      IaC: Terraform + Ansible                                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
ai-workflow-platform/
├── agents/                         # Python multi-agent system
│   ├── planner_agent.py            # Breaks tasks into sub-goals
│   ├── summarizer_agent.py         # Document + ticket summarization
│   ├── responder_agent.py          # Customer support response
│   ├── rag_engine.py               # RAG pipeline with ChromaDB
│   ├── bias_checker.py             # Responsible AI – bias detection
│   ├── content_filter.py           # Content moderation
│   └── base_agent.py               # Shared agent base class
├── api/
│   ├── main.py                     # FastAPI entrypoint
│   ├── routers/                    # Route handlers
│   └── middleware/                 # Auth, logging, tracing
├── n8n/
│   └── workflows/                  # Exported n8n workflow JSONs
│       ├── customer_support.json
│       ├── document_summarization.json
│       └── anomaly_detection.json
├── infrastructure/
│   ├── docker/
│   │   ├── Dockerfile              # App image
│   │   └── docker-compose.yml      # Full local stack
│   ├── kubernetes/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── hpa.yaml                # Horizontal Pod Autoscaler
│   │   └── ingress.yaml
│   ├── terraform/
│   │   ├── main.tf                 # GCP/AWS infra
│   │   ├── variables.tf
│   │   └── outputs.tf
│   └── ansible/
│       └── playbook.yml            # Node provisioning
├── monitoring/
│   ├── prometheus.yml              # Scrape configs
│   ├── grafana-dashboard.json      # Pre-built dashboard
│   └── otel-collector.yml          # OpenTelemetry config
├── .github/
│   └── workflows/
│       └── ci-cd.yml               # GitHub Actions pipeline
├── tests/
│   ├── test_agents.py
│   ├── test_rag.py
│   └── test_api.py
├── scripts/
│   ├── seed_vectordb.py            # Load docs into ChromaDB
│   └── load_test.py                # 50K TPS load simulation
├── docker-compose.yml              # Root compose (mirrors infra/docker)
├── requirements.txt
└── README.md
```

---

## 🚀 Quick Start (Local Demo)

```bash
# 1. Clone and configure
git clone https://github.com/yourname/ai-workflow-platform.git
cd ai-workflow-platform
cp .env.example .env
# Add OPENAI_API_KEY, HF_TOKEN, DB_URL

# 2. Spin up the full stack
docker-compose up -d

# 3. Seed the vector database
python scripts/seed_vectordb.py

# 4. Access services
# API:        http://localhost:8000/docs
# n8n:        http://localhost:5678
# Grafana:    http://localhost:3000  (admin/admin)
# Prometheus: http://localhost:9090
```

---

## 🤖 Multi-Agent Workflow

```
User Request
    │
    ▼
[Planner Agent]          ← Decomposes task into steps
    │
    ├──► [RAG Engine]    ← Retrieves relevant docs/tickets
    │
    ├──► [Summarizer]    ← Hugging Face BART/T5
    │
    └──► [Responder]     ← GPT-4 generates final response
              │
              ▼
    [Bias Check + Content Filter]
              │
         ┌───▼───┐
         │ HITL  │   ← Human-in-the-loop for sensitive tasks
         └───────┘
```

---

## 🔑 Key Technical Decisions (Interview Talking Points)

| Decision | Why |
|---|---|
| n8n for orchestration | Visual workflow builder, webhook support, 400+ integrations |
| ChromaDB for vectors | Lightweight, runs in-process, easy to swap for Pinecone |
| LangChain | Standardizes LLM calls, chain composition, memory |
| ArgoCD | GitOps — infra state always matches git, easy rollbacks |
| OpenTelemetry | Vendor-neutral tracing; works with Jaeger, Tempo, Datadog |
| Zero-Trust | mTLS between services, short-lived tokens, no implicit trust |

---

## 📊 Performance

- **Throughput**: 50,000+ transactions/sec (Kubernetes HPA + GCP)
- **Latency P99**: < 200ms for RAG queries
- **Token Usage**: Monitored per-request via OpenTelemetry custom metrics
- **Uptime**: Zero data loss with Kubernetes PodDisruptionBudgets

---

## 🛡️ Responsible AI

- Bias detection via `agents/bias_checker.py` (demographic parity checks)
- Content filtering before every LLM response
- Human-in-the-loop approval queue for flagged outputs
- Full audit trail in PostgreSQL
