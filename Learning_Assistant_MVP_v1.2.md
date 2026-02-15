# Learning Assistant — Canonical MVP Plan v1.2

> **Supersedes v1.1**  
> Adds **Cloud E2E Pilot** to make the MVP truly usable from a mobile phone anywhere.

---

## 0. MVP Definition

A personal AI assistant that can be **used anywhere from an Android phone**:
documents are ingested (URL/PDF), questions are answered reliably with RAG,
and the system builds longer-term understanding via S2 summaries and
Weekly Recommendations.

Knowledge Graph and production hardening are explicitly post-MVP.

---

## 1. Scope Lock

### Included in MVP (v1.2)

- URL / PDF ingest (async)
- Backend + PDF worker usability improvements
- **Cloud-hosted backend (public HTTPS endpoint)**
- Android ↔ Cloud Backend ↔ RAG full integration
- RAG with pgvector
- Rule-based eval + LLM judge + refine loop
- S1 summaries (feed)
- S2 consolidation (batch)
- Weekly Recommendation (Top-3 per topic)
- runs / events logging

### Explicitly Post-MVP

- Knowledge Graph (concepts / relations / UI)
- Production hardening (SLA, rate limit, caching)
- Cost optimization
- Observability dashboards
- Advanced retrieval heuristics
- UX polish beyond minimal flows
- Multi-tenant / multi-user support

---

## 2. Canonical MVP Architecture (Cloud)

Android App (Minimal)
- Query → Answer
- Share URL / PDF
- Ingest status (queued / running / done)
- S1 Feed
- Weekly Recommendations

Cloud Backend (FastAPI)
- POST /ingest
- GET  /ingest/status
- GET  /sources
- GET  /feed
- POST /rag/answer
- POST /jobs/s2
- POST /jobs/recommendations

LangGraph Workflows
- Ingest → Chunk/Embed → S1
- RAG → Eval → Judge → Refine
- S2 Consolidation (batch)
- Weekly Recommendation (batch)

Supabase (Managed)
- Postgres + pgvector
- Storage (PDFs)
- summaries (S1, S2)
- candidates / recommendations / rec_feedback
- runs / events

Secrets & Config
- Environment variables (API keys, DB URLs)
- No secrets on device

---

## 3. 10-Week Canonical MVP Schedule (v1.2)

### Week 1–2 — Ingest & S1 Foundation
- URL + PDF ingest
- Chunking (20–50 chunks/doc)
- Embeddings
- S1 summary
- Idempotent upsert
- Basic tests

Exit:
- Ingest success >95%
- No missing S1 summaries

---

### Week 3 — RAG v1
- /rag/answer
- pgvector kNN (k≈8)
- citations
- cannot-answer handling

Targets:
- Vector search <100 ms
- End-to-end <1.5 s

---

### Week 4 — Quality Guard & Refine Loop
- Rule-based eval
- LLM judge (faithfulness, coverage)
- Refine loop ≤2 (expand-k, query rewrite)
- Before/after score persistence

Targets:
- Refine trigger rate 10–40%
- p95 latency <3 s

---

### Week 5 — Android Minimal (Initial)
- Firebase gateway (optional)
- Android → Backend → Answer (basic)
- URL/PDF share entry point

Target:
- Mobile E2E success >95% (happy path)

---

### Week 6 — Usability & Integration Sprint
- Simplify backend + PDF worker execution
  - single-service deployment OR
  - job queue + clear status API
- Android ↔ RAG direct connection
- Ingest status visibility
- Remove PC-only manual testing paths

Required APIs:
- POST /ingest → {job_id}
- GET /ingest/status → {state, progress}
- GET /sources
- GET /feed

Exit:
- Android PDF ingest → status=done success >95%
- Android query → answer success >95%
- PDF ingest completion <60s (dev env)

---

### Week 7 — **Cloud E2E Pilot (NEW)**

**Goal:** Use the system from anywhere without a local PC.

Scope:
- Deploy FastAPI backend to cloud (public HTTPS)
- Run ingest + RAG fully in cloud
- Use managed DB + storage (Supabase)
- Android app points to cloud endpoint
- Secrets via environment variables

Exit:
- Android works on cellular network
- No local backend required
- Cloud E2E demo succeeds 3× consecutively

---

### Week 8 — S2 Consolidation (Long-Term Memory)
- Batch S2 generation (daily / weekly)
- Inputs: recent S1 + notes (optional) + previous S2
- Topic-level, versioned S2 summaries

Exit:
- 5–20 active topics
- Stable regeneration (idempotent)

---

### Week 9 — Weekly Recommendation Pipeline
- S2 topic enumeration
- Query expansion
- Candidate fetch (arXiv / RSS / web)
- Embed + score (relevance, novelty, recency)
- Top-3 per topic
- Feedback storage

Exit:
- ≤10 topics
- Top-3 generated per topic
- Retrievable from Android

---

### Week 10 — MVP Closure
- Demo scenarios:
  1) PDF → question → answer (cloud)
  2) Multiple docs → S2 summary
  3) Weekly Recommendations surfaced
- Metrics snapshot:
  - latency
  - refine rate
  - cannot-answer rate
- Post-MVP backlog finalized

---

## 4. Canonical Statement

"A cloud-hosted, mobile-first personal AI assistant that answers questions,
builds long-term understanding, and recommends new information —
ready for production hardening next."
