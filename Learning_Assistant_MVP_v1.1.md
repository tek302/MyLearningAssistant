# Learning Assistant — Canonical MVP Plan v1.1

> **Supersedes v1.0**  
> Focus: real usability first, then long-term memory & discovery.

---

## 0. MVP Definition

A personal AI assistant that can be **used end-to-end from the Android app**:
documents are ingested (URL/PDF), questions are answered reliably with RAG,
and the system gradually builds long-term understanding via S2 summaries and
Weekly Recommendations.

Knowledge Graph and production hardening are explicitly post-MVP.

---

## 1. Scope Lock

### Included in MVP (v1.1)

- URL / PDF ingest (async)
- Backend + PDF worker usability improvements
- Android ↔ Backend ↔ RAG full integration
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
- Retrieval heuristic research
- UX polish beyond minimal flows
- Multi-tenant / multi-user support

---

## 2. Canonical MVP Architecture

Android App (Minimal)
- Query → Answer
- Share URL / PDF
- Ingest status (queued / running / done)
- S1 Feed
- Weekly Recommendations

FastAPI Orchestrator
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

Supabase
- sources / chunks / embeddings
- summaries (S1, S2)
- candidates / recommendations / rec_feedback
- runs / events

---

## 3. 10-Week Canonical MVP Schedule (v1.1)

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
- Firebase gateway
- Android → Backend → Answer (basic)
- URL/PDF share entry point

Target:
- Mobile E2E success >95% (happy path)

---

### Week 6 — Usability & Integration Sprint (Priority)

**Goal:** End-to-end usability from the phone.

Scope:
- Simplify backend + PDF worker execution
  - single-service deployment OR
  - clear job queue + status API
- Android ↔ RAG direct connection
- Remove PC-only manual testing paths
- Ingest status visibility from Android

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

### Week 7 — S2 Consolidation (Long-Term Memory)
- Batch S2 generation (daily / weekly)
- Inputs: recent S1 + notes (optional) + previous S2
- Topic-level S2
- Versioned S2 summaries

Exit:
- Stable regeneration (idempotent)
- 5–20 active topics

---

### Week 8 — Weekly Recommendation Pipeline
- S2 topic enumeration
- Query expansion
- Candidate fetch (arXiv / RSS / web)
- Embed + score (relevance, novelty, recency)
- Top-3 per topic
- Feedback storage

Exit:
- ≤10 topics
- Top-3 generated per topic
- Stored and retrievable via API

---

### Week 9 — Integration
- S2 → Recommendation linkage
- Android displays Weekly Recommendations
- Async ingest stabilization
- Retry / checkpoint cleanup

Exit:
- End-to-end Rec flow usable from Android
- Ingest failure <5%

---

### Week 10 — MVP Closure
- Demo scenarios:
  1) PDF → question → answer
  2) Multiple docs → S2 summary
  3) Weekly Recommendations surfaced
- Metrics snapshot:
  - latency
  - refine rate
  - cannot-answer rate
- Post-MVP backlog finalized

---

## 4. Canonical Statement

"A usable personal AI assistant that answers questions, summarizes knowledge,
and recommends new information — ready for production hardening next."
