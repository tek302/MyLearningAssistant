# 🧠 Learning Agent MVP Plan v0.2
**Stack:** Firebase Gateway + LangChain/LangGraph Orchestrator + Supabase(pgvector)  
**Focus:** Long-term memory (S1→S2→PKG) persistence and LangGraph↔Supabase integration

---

## 0️⃣ System Overview (Updated Architecture)

```
Android App
  ├─ Auth(Firebase) / Retrofit / FCM
  ├─ UI: Feed · Note · MindMap
  └─ Upload/Highlight → Firebase Functions

Firebase Gateway
  ├─ Functions (HTTP): /ingest /feed /notify
  ├─ Scheduler & Pub/Sub (periodic crawl)
  ├─ Firestore (cache, read markers)
  └─ FCM Push

Orchestrator (FastAPI + LangGraph)
  ├─ Nodes: Ingest → Chunk&Embed → Summarize.S1 → Consolidate.S2 → PKG.Update
  ├─ LangGraph StateGraph (Plan→Search→Evaluate→Refine→Synthesize)
  ├─ Tools: Fetcher · Embedder · Summarizer · Evaluator · Refiner
  ├─ Repo: Supabase(Postgres+pgvector) read/write
  ├─ Checkpoints & Logs: runs / checkpoints / events
  └─ Storage(GCS) for PDFs & snapshots

Supabase
  ├─ Postgres + pgvector (core memory DB)
  │    ├─ sources / chunks / embeddings
  │    ├─ summaries(S1,S2) / notes
  │    ├─ concepts / relations (PKG)
  │    └─ runs / checkpoints / events
  └─ Storage: raw files & images
```

### 🧭 Data Flow (Conceptual)
```
User → /ingest(URL) → LangGraph
  (1) fetch & parse → sources
  (2) chunk & embed → chunks / embeddings
  (3) summarize S1 → short-term memory
  (4) consolidate S2 → long-term topic/global memory
  (5) PKG.update → concepts/relations (knowledge graph)
  ↓
Supabase persists → Android reads via /feed, /memory, /graph
```

---

## 1️⃣ Long-Term Memory Lifecycle

| Stage | Description | Stored Table | Frequency |
|--------|--------------|--------------|------------|
| **S1** | Doc-level TL;DR + bullets + actions | `summaries(scope='doc', kind='S1')` | On ingest |
| **S2** | Topic/global consolidation summary (compression of S1 + notes) | `summaries(scope='topic', kind='S2')` | Daily |
| **PKG** | Personal Knowledge Graph (concepts + relations) | `concepts`, `relations` | Weekly |
| **Notes** | Highlights, reflections | `notes` | Continuous |

**Pipeline**
```
Ingest → Summarize.S1
       → Consolidate.S2 (merge old S2 + new S1 + notes)
       → PKG.Update (NER+similarity→concept merge, relation inference)
```

**Retention**
- Raw chunks/embeddings kept indefinitely  
- S1 compressed into S2 versions (archived after merge)  
- Cold files moved to cheaper storage

---

## 2️⃣ LangGraph ↔ Supabase Integration

### 🔹 Components
- **SupabaseRepo**: unified read/write layer  
  - CRUD via `supabase-py` (sources, notes, summaries)  
  - Vector ops via `psycopg` raw SQL (`embedding <-> q.emb`)  
- **LangGraph Nodes** use Repo via DI  
  - `node_ingest()` → upsert sources/chunks/embeddings  
  - `node_summarize_s1()` → insert summaries(S1)  
  - `node_consolidate_s2()` → read S1 + notes → generate S2  
  - `node_pkg_update()` → upsert concepts / relations  
- **State (`AgentState`)**: `{user_id, query, hits, draft, score, retries, ...}`  
- **Checkpoints/Events** tables log node-level execution for reproducibility  

---

### 🔹 Execution Relationship Diagram  

```
┌─────────────────────────── LangGraph Orchestrator ───────────────────────────┐
│                                                                               │
│  [Node: Ingest] ──────────────────────────────────────────────┐              │
│     fetch+parse (web_fetch.py)                                │              │
│        ↓                                                      │              │
│     SupabaseRepo.upsert_source()  →  INSERT sources            │              │
│     SupabaseRepo.insert_chunks() →  INSERT chunks              │              │
│        ↓                                                      │              │
│  [Node: Chunk&Embed]                                          │              │
│     Embed each chunk → repo.upsert_embeddings() → pgvector     │              │
│        ↓                                                      │              │
│  [Node: Summarize.S1]                                         │              │
│     LLM summarizer → repo.insert_summary(kind='S1')            │              │
│        ↓                                                      │              │
│  [Node: Consolidate.S2]                                       │              │
│     Read S1+Notes → LLM consolidation → repo.insert_summary(‘S2’) │           │
│        ↓                                                      │              │
│  [Node: PKG.Update]                                           │              │
│     Extract/merge concepts → repo.upsert_concept()             │              │
│     Derive relations → repo.upsert_relation()                  │              │
│        ↓                                                      │              │
│  [Node: Evaluate/Refine]                                      │              │
│     grade() → repo.insert_event() / update_score               │              │
│                                                                               │
└───────────────────────────────────────────────────────────────────────────────┘

Supabase Tables Affected:
  - sources, chunks, embeddings
  - summaries (S1/S2)
  - notes
  - concepts, relations
  - runs, checkpoints, events
```

---

### 🔹 Typical Query Examples
**Vector search**
```sql
WITH q AS (SELECT $1::vector AS emb)
SELECT c.source_id, c.ord, c.text
FROM embeddings e
JOIN chunks c ON c.id = e.chunk_id
JOIN sources s ON s.id = c.source_id, q
WHERE s.user_id=$2 AND s.lang IN ('en','ko')
ORDER BY e.embedding <-> q.emb
LIMIT 8;
```

**S2 consolidation (pseudo-code)**
```python
def consolidate_topic_summaries(user_id, topic):
    s1 = fetch_recent_S1(user_id, topic)
    notes = fetch_notes(user_id, topic)
    prev = fetch_latest_S2(user_id, topic)
    prompt = build_prompt(s1, notes, prev)
    s2 = llm(prompt, max_tokens=1200)
    repo.insert_summary({
       "user_id": user_id, "scope": "topic", "kind": "S2",
       "version": prev.version+1, **s2
    })
```

---

## 3️⃣ Core Schema (Long-Term Memory–Focused)

- `summaries` — stores S1/S2 versions  
- `concepts` & `relations` — PKG graph  
- `notes` — user highlights  
- `runs`, `checkpoints`, `events` — LangGraph trace  

Each table enforces `user_id` RLS for isolation.

---

## 4️⃣ Updated 9-Week Roadmap (v0.2)

| Week | Goal | Major Deliverables |
|------|------|--------------------|
| **W1–2** | Baseline setup | Firebase + Supabase connectivity / Orchestrator skeleton |
| **W3** | Ingest & S1 summarization | `/ingest/url`, chunks/embeddings, S1 summary |
| **W4** | RAG answer API & Android feed | `/rag/answer` with citations |
| **W5** | **Memory Consolidation (S2)** | Daily job + S2 table insert + evaluation loop |
| **W6** | Notes + Highlight Module | `/notes` API + Android UI |
| **W7** | **PKG (Mind Map v0)** | concept extraction + relation inference + Next.js visualization |
| **W8** | Observability / Dashboard | Token cost / latency metrics, OpenTelemetry |
| **W9** | Beta release & RLS hardening | Policies / User onboarding / Feedback |

---

## 5️⃣ Mind Map & PKG Visualization

- Web (Next.js + Cytoscape.js)  
- Node importance = `notes_count + citations + recency_weight`  
- Edge weight = `co-occurrence + semantic similarity`  
- Features: topic/date filters, k-hop view, diff, export(SVG/PNG)

---

## 6️⃣ Auth & Security
- Android → Firebase ID Token → Functions → Orchestrator  
- Orchestrator verifies token → maps `firebase_uid` ↔ Supabase `user_id`  
- RLS enforces per-user row isolation  
- Supabase Service Key only for server access  
- Storage objects under user-scoped paths (`/user/{uid}/...`)

---

## 7️⃣ Daily / Weekly Jobs (Scheduler)

| Job | Schedule | Function |
|------|-----------|----------|
| S2 Consolidation | daily 03:00 | Merge recent S1 + notes → S2 |
| PKG Update | weekly Sun 04:00 | Concept merge + relation refresh |
| Cleanup | hourly | Remove orphan chunks / stale runs |
| Health | hourly | pgvector stats, token cost summary |

---

## 8️⃣ Key Metrics

| Metric | Target | Source |
|---------|---------|---------|
| Faithfulness score | ≥ 0.85 | LLM rubric |
| Summary coverage | ≥ 0.7 | #docs in S2 / total |
| Duplication rate | ≤ 10 % | overlap check |
| Graph accuracy | ≥ 95 % correct relations | manual sample |
| Recall latency | < 100 ms | pgvector query |

---

## 9️⃣ References & Learning

- **LangGraph Docs:** https://langchain-ai.github.io/langgraph/  
- **Supabase pgvector Guide:** https://supabase.com/docs/guides/database/extensions/pgvector  
- **FastAPI Docs:** https://fastapi.tiangolo.com/  
- **LangChain Blog:** 👉 *Build a Personalized RAG Agent with Supabase* (2024) — closest architecture example.

---

**Version:** v0.2 (Integrating Long-Term Memory and LangGraph↔Supabase Workflow)
