# Learning Assistant — Canonical MVP Plan v1.0

## 0. MVP Definition

A personal AI assistant that ingests my documents, provides reliable RAG answers,
accumulates long‑term knowledge via S2 summaries and a Knowledge Graph,
and surfaces Weekly Recommendations — without production hardening.

---

## 1. Scope Lock

### Included in MVP
- URL / PDF ingest (async)
- RAG with pgvector
- Rule-based eval + LLM judge + refine loop
- S1 summaries
- S2 consolidation (batch)
- Knowledge Graph (concepts / relations)
- Weekly Recommendation (Top‑3 per topic)
- Android minimal client
- runs / events logging

### Explicitly Post‑MVP
- Production hardening (SLA, rate limit, caching)
- Cost optimization
- Observability dashboards
- Retrieval heuristic research
- UX polish
- Multi‑tenant / multi‑user

---

## 2. Architecture (MVP)

Android App (Minimal)
- Query → Answer
- Share URL / PDF
- S1 Feed / S2 Summary
- Weekly Recommendations

FastAPI Orchestrator
- /ingest (async)
- /rag/answer
- /jobs/s2
- /jobs/pkg
- /jobs/recommendations
- /graph/export

LangGraph
- Ingest → Chunk/Embed → S1
- RAG → Eval → Judge → Refine
- S2 Consolidation
- PKG Update
- Weekly Recommendation

Supabase
- sources / chunks / embeddings
- summaries (S1, S2)
- concepts / relations
- candidates / recommendations / rec_feedback
- runs / events

---

## 3. 10‑Week Canonical MVP Schedule

### Week 1–2 — Ingest & S1 Foundation
- URL + PDF ingest
- Chunking (20–50 chunks/doc)
- Embeddings
- S1 summary
- Idempotent upsert
- Basic tests

Exit:
- Ingest success >95%
- No missing S1

---

### Week 3 — RAG v1
- /rag/answer
- pgvector kNN (k≈8)
- citations
- cannot‑answer handling

Targets:
- Vector search <100 ms
- E2E <1.5 s

---

### Week 4 — Quality Guard & Refine
- Rule-based eval
- LLM judge (faithfulness, coverage)
- Refine loop ≤2
- Score persistence

Targets:
- Refine rate 10–40%
- p95 latency <3 s

---

### Week 5 — Android Minimal
- Firebase gateway
- Android → Backend → Answer
- URL/PDF share

Target:
- Mobile E2E success >95%

---

### Week 6 — S2 Consolidation
- Batch S2 generation
- Inputs: S1 + notes + previous S2
- Topic‑level, versioned S2

---

### Week 7 — Knowledge Graph (PKG v1)
- Concept extraction
- Relation inference (co‑occurrence, S2‑based)
- /graph/export API

---

### Week 8 — Weekly Recommendation
- S2 topic enumeration
- Candidate fetch
- Embed + score
- Top‑3 per topic
- Feedback storage

---

### Week 9 — Integration
- RAG ↔ S2 context
- KG ↔ Recommendation query expand
- Async ingest stabilization

---

### Week 10 — MVP Closure
- Demo scenarios (RAG, S2, KG, Weekly Rec)
- Metrics snapshot
- Post‑MVP backlog finalized

---

## 4. Canonical Statement

"A complete personal knowledge assistant that answers, summarizes,
connects, and recommends — ready for production hardening next."
