# Learning Agent MVP – Development Plan v0.5

## Current Status
- Week1: Supabase / project bootstrap ✅
- Week2: Ingest (HTML + PDF), chunking, embeddings, S1 summary, idempotent upsert, pytest automation ✅

---

## Updated 8-Week Development Plan

### Week3 — RAG v1 (Direct Implementation → LangGraph Migration)
**Goal:** End-to-end RAG works with citations.

**Week3.1: Direct RAG Implementation**
- POST /rag/answer
  - Query embedding
  - pgvector top-k search (k=8)
  - Simple filtering (topic/lang)
  - LLM synthesis with citations
- Persist minimal runs/events
- Tests:
  - Basic RAG success
  - Latency sanity check

**Week3.2: LangGraph Migration**
- Convert RAG flow to LangGraph:
  - EmbedQuery → Retrieve → (ReRank) → Synthesize → Persist
- Add node-level retry & logging
- Router only calls graph runner
- Tests unchanged (behavioral parity)

---

### Week4 — Quality Guard & Refine Loop
**Goal:** Agentic refinement when quality is low.

- Evaluate node:
  - faithfulness / coverage / recency
- Refine loop if score < 0.75:
  - expand k or rewrite query
- Persist before/after scores
- Tests for refine trigger

---

### Week5 — Android Integration (Minimal)
**Goal:** Android query → answer roundtrip.

- Firebase Gateway proxy for RAG
- Firebase Auth (or bypass)
- Minimal Android UI
- Gateway integration test

---

### Week6 — S2 Consolidation & Weekly Top3 Recommendations
**Goal:** Weekly recommendations per S2 topic.

- S2 consolidation batch
- Weekly Top3 pipeline:
  - Candidate fetch (arXiv / web)
  - LLM ranking + summary
  - Store in recommendations table
- Notification payload prep

---

### Week7 — Knowledge Graph / Mindmap (v1)
**Goal:** Visualize personal knowledge graph.

- PKG update batch (concepts/relations)
- Graph export API
- Simple web visualization (D3/Cytoscape)

---

### Week8 — Hardening & MVP Closure
**Goal:** Operational readiness.

- Rate limit & caching
- Retry / checkpoint hardening
- Cost & latency metrics
- Docs + demo scenarios

---

## Key Strategy
- Prioritize E2E confirmation early
- Migrate to LangGraph as soon as flow stabilizes
- Build toward agentic refinement and long-term memory
