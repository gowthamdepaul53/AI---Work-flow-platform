# Interview Talking Points — AI Workflow Orchestration Platform

> Use this as your prep guide. Each section maps to a common interview question pattern.

---

## "Walk me through the architecture."

**Start with the flow, not the tech:**

> "The platform automates customer support end-to-end. When a ticket comes in via webhook,
> it triggers an n8n workflow that coordinates three specialized AI agents — a Planner,
> a Summarizer, and a Responder — each with a specific role. Before any response reaches
> the customer, it passes through bias detection and content filtering, and sensitive cases
> go to a human review queue. The whole thing runs on Kubernetes and emits traces and
> metrics to our observability stack."

**Then draw the box diagram:**
```
Webhook → n8n → [Planner → RAG → Summarizer → Responder] → Safety → HITL → Customer
```

---

## "Why n8n instead of [Airflow / Prefect / custom code]?"

- **Visual debugging**: non-engineers (product, support leads) can see and modify workflows
- **Webhook-native**: built for event-driven patterns, not batch jobs
- **400+ integrations**: Slack, Postgres, Gmail, Salesforce — no custom connectors
- **Retry/error handling**: built-in, with dead-letter routing
- **Self-hosted**: we own our data, no SaaS vendor lock-in
- *Airflow is batch-first, overkill for request-response flows*

---

## "How does RAG work in this system?"

> "We embed support documents and historical tickets using OpenAI's text-embedding-3-small
> model (1536 dimensions) and store them in ChromaDB. At query time, the user's ticket is
> embedded and we do cosine similarity search to retrieve the top-5 most relevant chunks.
> Those chunks are injected into the LLM's context as grounding — the model can only
> answer based on retrieved content, which reduces hallucination significantly."

**Key numbers to remember:**
- Embedding model: `text-embedding-3-small` (cheap, fast, high quality)
- Vector DB: ChromaDB (swap to Pinecone for managed/prod)
- Top-k: 5 chunks
- Similarity metric: cosine

---

## "Explain the multi-agent design."

> "Each agent has a single responsibility:
> - **Planner**: takes a raw task and produces a step-by-step execution plan in JSON
> - **Summarizer**: condenses tickets using HuggingFace BART (short) or GPT-4 (long)
> - **Responder**: generates customer-facing replies grounded in the summary + RAG context
>
> n8n routes between them — it's the orchestration layer. The agents don't call each other
> directly; they're decoupled through the workflow. This means I can swap any agent
> independently, A/B test different models, or add a new agent without touching the others."

---

## "What Responsible AI measures did you implement?"

Three layers — be specific:
1. **Bias detection** (`bias_checker.py`): lexical scan + regex for known bias patterns, demographic parity checks, optional GPT-4 meta-eval
2. **Content filtering** (`content_filter.py`): harmful keyword blocklist, PII regex detection + redaction, OpenAI Moderation API
3. **Human-in-the-loop**: flagged outputs route to a `hitl_queue` table; a human reviews before the response is sent; audit trail in PostgreSQL

---

## "How did you achieve 50K TPS?"

> "The API is stateless — every instance can handle any request. We deployed on Kubernetes
> with a Horizontal Pod Autoscaler configured to scale from 3 to 20 pods based on CPU and
> memory. In GCP, the node pool auto-scales up to handle burst traffic.
>
> Key design choices:
> - Async FastAPI with 4 Uvicorn workers per pod
> - Connection pooling to PostgreSQL (AsyncPG)
> - ChromaDB queries are in-memory for low latency
> - PodDisruptionBudgets ensure zero data loss during node drain"

**Load test command:**
```bash
python scripts/load_test.py --url http://api:8000 --rps 1000 --duration 60
```

---

## "Explain your CI/CD pipeline."

```
git push → GitHub Actions
  1. Ruff lint + mypy type check
  2. pytest (mocked LLM, real Postgres in CI)
  3. Docker build + push to GCR (multi-stage, ~200MB image)
  4. Update K8s manifest with new image tag
  5. git commit manifest → ArgoCD detects change
  6. ArgoCD syncs cluster → Rolling deploy, zero downtime
```

**Why ArgoCD (GitOps)?**
- Git is the source of truth — rollback = `git revert`
- No CI pipeline needs `kubectl` access (security)
- Self-healing: if someone manually changes K8s, ArgoCD reverts it

---

## "How did you handle observability?"

Three pillars:
- **Metrics** (Prometheus + Grafana): HTTP request rate, latency histograms, token usage/cost, error rates
- **Traces** (OpenTelemetry → Jaeger): end-to-end spans across agents, RAG queries, DB calls
- **Logs** (structured JSON → CloudLogging): every agent call logged with ticket_id, tokens, latency

**Custom metrics tracked:**
- `ai_platform_tokens_total{agent="summarizer"}` — token spend per agent
- `ai_platform_rag_latency_ms` — RAG query duration
- `ai_platform_hitl_queue_depth` — backlog of flagged outputs

---

## "What would you improve if you had more time?"

Strong answer shows you think about production maturity:
1. **Streaming responses**: use OpenAI streaming API to reduce perceived latency
2. **Caching**: semantic cache — if a new ticket is >95% similar to a past one, return cached response
3. **Fine-tuning**: fine-tune a smaller model (GPT-3.5 or Llama 3) on our resolved tickets to reduce GPT-4 costs
4. **Evaluation pipeline**: automated LLM-as-judge scoring every response against a golden dataset
5. **Multi-region**: active-active GCP + AWS for disaster recovery

---

## Metrics to quote in interviews

| Metric | Value |
|---|---|
| Throughput | 50,000+ TPS |
| RAG latency P99 | < 200ms |
| Uptime | Zero data loss (PodDisruptionBudget) |
| Image size | ~200MB (multi-stage Docker) |
| Agents | 3 (Planner, Summarizer, Responder) |
| Vector collections | 2 (knowledge base, historical tickets) |
| CI pipeline time | ~4 min (lint → test → build → deploy) |
