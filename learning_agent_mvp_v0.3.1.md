# 🧠 Learning Agent MVP Plan v0.3
**Stack:** Firebase Gateway + LangChain/LangGraph Orchestrator + Supabase(pgvector)  
**Focus:** Long-term memory (S1→S2→PKG) persistence, LangGraph↔Supabase integration, and UX Scenarios

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

## 3️⃣ UX Scenario Map (User Journey + System Flow)

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                             📱 Android Learning App                            │
│───────────────────────────────────────────────────────────────────────────────│
│ ① Share → /ingest(URL, PDF)      ② Feed: 요약(TL;DR, bullets) 보기           │
│ ③ Highlight → /notes              ④ Ask Question (/rag/answer)                │
│ ⑤ Weekly Briefing / Mind Map 탐색                                              │
└──────────────┬───────────────────────────────────────────────────────────────┘
               │  (Bearer Firebase ID Token)
               ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                           ☁️ Firebase Gateway (GCF)                            │
│───────────────────────────────────────────────────────────────────────────────│
│ /ingest  /feed  /notify   (Auth verify, Scheduler, FCM push, Firestore cache) │
└──────────────┬───────────────────────────────────────────────────────────────┘
               │   (REST proxy call)
               ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                 ⚙️ Orchestrator API (FastAPI + LangGraph Runner)              │
│───────────────────────────────────────────────────────────────────────────────│
│ /ingest/url      → LangGraph: Ingest → Chunk&Embed → Summarize.S1             │
│ /rag/answer      → Search → Summarize.withCitations                           │
│ /notes, /graph, /briefings API                                                 │
│ Auth verify(Firebase Token → user_id)                                         │
└──────────────┬───────────────────────────────────────────────────────────────┘
               │
               ▼
┌────────────────────────────── LangGraph Workflow ─────────────────────────────┐
│ [Ingest] → [Chunk&Embed] → [Summarize.S1] → [Consolidate.S2] → [PKG.Update]   │
│                ↘                              ↘                               │
│                 [Evaluate/Refine]             [Checkpoint/Events]              │
└──────────────┬───────────────────────────────────────────────────────────────┘
               │   (via SupabaseRepo)
               ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                        🗄️ Supabase (Postgres + pgvector)                       │
│───────────────────────────────────────────────────────────────────────────────│
│ Tables: sources, chunks, embeddings, summaries(S1,S2), notes,                 │
│          concepts, relations, runs, checkpoints, events                       │
│ Storage: 원문 PDF / 스냅샷                                                    │
└──────────────┬───────────────────────────────────────────────────────────────┘
               │
               ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                        🔁 Android User Feedback Loop                           │
│───────────────────────────────────────────────────────────────────────────────│
│  - Feed 요약 업데이트 (Firestore 캐시 + Supabase summaries)                   │
│  - 새 S2/브리핑 생성 시 → Firebase FCM Push                                  │
│  - Mind Map 탐색 (concepts/relations 기반 시각화)                            │
│  - 개인 지식 성장 로그 (runs/events)                                         │
└───────────────────────────────────────────────────────────────────────────────┘
```

---

## 4️⃣ User Capabilities Summary

| 카테고리 | 사용자가 하는 일 | 내부 동작 | 저장 위치 |
|-----------|------------------|-------------|-------------|
| 자료 인제스트 | 기사, 논문, PDF 공유 | Ingest/Chunk/Embed/Summarize.S1 | sources, chunks, embeddings, summaries |
| 요약 피드 | TL;DR 확인 | Firestore 캐시 + summaries | summaries |
| 노트/메모 | 하이라이트, 태그 | /notes API | notes |
| 검색/질문 | RAG 질의 | pgvector 검색 + LLM | embeddings, chunks |
| 주간 브리핑 | S2 Consolidation | daily/weekly job | summaries(S2) |
| Mind Map | 지식 관계 탐색 | PKG view | concepts, relations |

---

## 5️⃣ Learning Assistant Role Alignment

| 역할 범주 | 지원 상태 | 세부 내용 |
|------------|------------|------------|
| 정보 수집 & 요약 | ✅ | 웹 기사·논문 인제스트 → 요약 자동 생성 |
| 개인 노트 / 하이라이트 | ✅ | 노트 저장·태깅·검색 |
| 지속적 지식 축적(Long-term Memory) | ✅ | S1→S2 자동 통합, 주제별 버전관리 |
| 지식 구조화 (그래프) | ✅ | 개념 추출 + 관계 추론 → Mind Map 시각화 |
| 리마인드 / 주간 브리핑 | ✅ | S2 Consolidation Job + /briefings |
| 지식 탐색 / RAG 질의응답 | ✅ | pgvector 검색 + LLM 답변 + 인용 |
| 학습 진행 피드백 | ⚙️ | runs/events 기반 리포트 or 메트릭 요약 |
| 학습 추천/다음 주제 안내 | 🔜 | PKG centrality + recency 분석으로 추천 |

---

**Version:** v0.3 (UX Scenarios + Long-Term Memory + LangGraph Integration)

---

## 🔎 Appendix — End-to-End Flow (Android → Firebase → Orchestrator → Supabase)

아래는 인제스트/요약 경로와 질의/RAG 경로를 모두 포함한 전체 플로우입니다. (사용자 정리안 반영)

```text
┌───────────────────────────────────────────────────────────────────────────────┐
│                                 Android App                                  │
│  (Firebase Auth, Retrofit, FCM, Share→/ingest)                                │
└───────────────┬───────────────────────────────────────────────────────────────┘
                │ 1) Authorization: Firebase ID Token
                ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                            Firebase Gateway (GCF)                             │
│  /ingest   /feed   /notify   (Scheduler/PubSub, Firestore: 캐시/리드마커)      │
└───────┬───────────────────────────────────────────┬───────────────────────────┘
        │2) /ingest 프록시                         │2’) /feed 프록시
        ▼                                           ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                  Orchestrator API (FastAPI + LangGraph Runner)               │
│  /ingest/url   /rag/answer   /notes   /graph/view   /briefings               │
│  (Firebase ID 토큰 검증 → user_id 매핑)                                       │
└───────┬───────────────────────────────────────────────────────────────────────┘
        │ 3) LangGraph 실행 (StateGraph; node별 retry/ckpt)
        ▼
     ┌──────────────────────── LangGraph Nodes / Tools ────────────────────────┐
     │ [Ingest] → [Chunk&Embed] → [Summarize.S1] → [Consolidate.S2] → [PKG.Up] │
     │                    ↘                          ↘                         │
     │                      [Evaluate/Refine]         [Save Checkpoint/Events] │
     └──────────────┬──────────────────────────────────────────────────────────┘
                    │ 4) Repo I/O (SupabaseRepo: supabase-py + psycopg SQL)
                    ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                                Supabase (DB)                                  │
│  Postgres + pgvector (core memory DB)                                         │
│   - sources / chunks / embeddings                                             │
│   - summaries(S1,S2) / notes                                                  │
│   - concepts / relations (PKG)                                                │
│   - runs / checkpoints / events                                               │
│  Storage: 원문 PDF/스냅샷                                                     │
└───────────────────────────────────────────────────────────────────────────────┘

반환: Orchestrator → Firebase → Android (요약/근거/메타)
푸시: Firebase /notify → FCM
```

### A) 인제스트/요약(메모리 축적) 시퀀스(요약)
1. Android → GCF /ingest {url, topic?} (Bearer idToken)  
2. GCF → Orchestrator /ingest/url (토큰 전달)  
3. FastAPI 검증(verifyIdToken) → user_id 매핑  
4. LangGraph:  
   4.1 [Ingest] fetch/parse → INSERT sources, chunks  
   4.2 [Chunk&Embed] embed → UPSERT embeddings(pgvector)  
   4.3 [Summarize.S1] LLM TL;DR → INSERT summaries(kind='S1')  
   4.4 [Evaluate/Refine] score<0.75면 재시도(옵션) → events/runs 기록  
   4.5 [Consolidate.S2] (배치/주기) S1+notes 통합 → INSERT summaries(kind='S2')  
   4.6 [PKG.Update] 개념/관계 추론 → UPSERT concepts, relations  
5. 결과 요약/메타 반환 → Android, 신규 항목은 FCM 알림(옵션)

**Supabase 쓰기 포인트(정량):**
- sources: 1건/URL, 평균 chunks 20–50건  
- embeddings: 청크 수만큼(1536D)  
- summaries: S1=문서당 1, S2=토픽당 버전↑  
- concepts/relations: 주간 배치에서 증분

### B) 질의/RAG(검색·회상) 시퀀스(요약)
1. Android → GCF /feed 또는 Orchestrator /rag/answer {query, k}  
2. Orchestrator:  
   2.1 임베딩(query) → pgvector kNN (embeddings <-> q) LIMIT k  
   2.2 상위 청크 re-rank/필터(언어/토픽/노트가중)  
   2.3 LLM synthesize with citations → 근거 [S{source}#C{ord}]  
   2.4 runs/events 기록(토큰/지연/스코어)  
3. 응답(JSON): answer + citations[] + meta(출처, 점수)

**평균 지연 목표:** k=8 기준 pgvector 질의 < 100ms(인덱스/캐시 전제)  
**품질 가드:** faithfulness/coverage/recency ≥ 0.75 미만 시 Refine 루프 1–2회

### C) 주기 잡(메모리 컨솔리데이션/그래프 갱신)
- Daily 03:00: Consolidate.S2 (최근 S1+노트 → S2 버전+1)  
- Weekly 04:00: PKG.Update (개념 병합/관계 리프레시)  
- Hourly: Cleanup(orphan), Health(pgvector 통계), 비용 요약
