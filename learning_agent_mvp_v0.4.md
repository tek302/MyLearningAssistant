# 🧠 Learning Agent MVP Plan v0.4
(Full Architecture + Workflows + 8-Week Development Plan)

---

## 0. System Architecture (Big Picture)

```text
Android App
  ├─ Firebase Auth / FCM / Retrofit
  ├─ Share → /ingest
  ├─ Feed (S1) / Notes / Mind Map (PKG)
  └─ Weekly Briefing (S2 + Recommendations)

Firebase Gateway (GCF)
  ├─ /ingest /feed /notify proxy
  ├─ Scheduler / PubSub
  └─ Firestore cache

Orchestrator (FastAPI + LangGraph)
  ├─ /ingest/url  /rag/answer /notes /graph /briefings
  ├─ /recommendations  /jobs/*
  ├─ Firebase Token verification → user_id
  └─ LangGraph Workflows

LangGraph Workflows
  Ingest → Chunk&Embed → Summarize.S1 → Consolidate.S2 → PKG.Update
                  ↘                       ↘
                Evaluate                 Checkpoint/Events

  RAG.Query → VectorSearch → AnswerWithCitations → Evaluate

  WeeklyRec:
    TopicEnumerate → QueryExpand → FetchCandidates → EmbedScore
                                 ↘ MMR/Dedup → Persist+Notify

Supabase (Postgres + pgvector)
  sources / chunks / embeddings
  summaries(S1,S2) / notes
  concepts / relations
  runs / checkpoints / events
  candidates / recommendations / rec_feedback
  Storage(PDF)
```

---

## 1. Data / Memory Model Summary

| Layer | Tables |
|-------|--------|
| Short-term memory (S1) | `summaries(scope='doc', kind='S1')` |
| Long-term memory (S2) | `summaries(scope='topic', kind='S2')` |
| Notes | `notes` |
| Knowledge Graph | `concepts`, `relations` |
| Execution trace | `runs`, `checkpoints`, `events` |
| Recommendation candidates | `candidates` |
| Weekly Top-3 results | `recommendations` |
| Feedback | `rec_feedback` |

---

## 2. Workflow A — Ingest / Summarize / Memory Accumulation

```text
Android → /ingest → Firebase GCF → Orchestrator /ingest/url
  ↓
LangGraph: 
  [Ingest]         → INSERT `sources`, `chunks`
  [Chunk&Embed]    → UPSERT `embeddings`
  [Summarize.S1]   → INSERT `summaries(kind='S1')`
  [Evaluate]       → `runs` / `events`
  [Consolidate.S2] (daily job)
  [PKG.Update]     (weekly job)

Supabase ← persistent memory
Firebase /notify → Android feed update (optional)
```

**Supabase writes (typical per document):**

- `sources`: 1 row  
- `chunks`: 20–50 rows  
- `embeddings`: 20–50 vectors (1536D)  
- `summaries` S1: 1 row  

---

## 3. Workflow B — RAG Query / Recall

```text
Android → /rag/answer → Firebase GCF → Orchestrator
  ↓
LangGraph RAG:
  [RAG.Query]       → query embedding
  [VectorSearch]    → pgvector kNN (embeddings <-> q)
  [AnswerWithCitations] → LLM answer + citations
  [Evaluate]        → events / runs

Supabase (embeddings, chunks)
Android displays answer + citations
```

- pgvector query latency target: **< 100 ms** (k≈8)  
- End-to-end answer latency: **수백 ms ~ 1초대** 목표  

---

## 4. Workflow C — S2 & PKG Batch (Long-term Memory)

### S2 Consolidation (Daily 03:00)

```text
S1(recent) + notes + previous S2
  → LLM consolidate
    → INSERT `summaries(scope='topic', kind='S2', version++)`
```

### PKG Update (Weekly 04:00)

```text
S2 → concept extraction → relation inference
  → UPSERT `concepts`, `relations`
```

---

## 5. Workflow D — Weekly Top-3 Recommendations

### Full Pipeline

```text
Cloud Scheduler (Weekly)
  ↓
Orchestrator `/jobs/recommendations/run`
  ↓
LangGraph WeeklyRec:
  [TopicEnumerate]  -- active S2 topics
  [QueryExpand]     -- keywords from S2 + concepts
  [FetchCandidates] -- arXiv/RSS/News API fetch (최근 7–14일)
  [EmbedScore]      -- Rel/New/Qual/Rec score
  [MMR/Dedup]       -- 다양성 확보, 중복 제거
  [Persist+Notify]  -- INSERT `recommendations` + FCM push

Supabase (`candidates`, `recommendations`, `rec_feedback`)
Android → Weekly Briefing View
```

### Scoring Details

```text
Rel = cos(topic_vec, candidate_vec)
New = min_distance(candidate_vec, past_LTM_vecs)
Qual = source_prior + citation/author_weight
Rec = exp(-Δdays/τ)   (τ ≈ 14)

Total = 0.45*Rel + 0.25*New + 0.20*Qual + 0.10*Rec
```

- Topic embedding: `topic_vec = mean( embed(S2_text), embed(top_k_concepts) )`  
- Candidate embedding: `embed(title + abstract)`  

### Android UX (Recommendations)

- Weekly 탭 → topic chip 선택 → Top-3 카드
- 카드 정보: title, source, published_at, short summary, score bar
- 액션: 👍 up / 👎 down / 💾 save / ✕ dismiss → `rec_feedback` 저장
- 딥링크: 기사 열기 + 관련 S2 / 관련 notes 화면으로 이동

---

## 6. End-to-End Call Flow (All Paths)

```text
┌───────────────────────────────────────────────────────────────────────┐
│ Android App                                                           │
│  - Share→/ingest                                                      │
│  - Feed (S1), Notes                                                   │
│  - RAG Query                                                          │
│  - Weekly Briefing & Recommendations                                  │
└───────────────────────┬───────────────────────────────────────────────┘
                        ▼
Firebase Gateway (GCF)
  - /ingest /feed /notify proxy
  - Scheduler / PubSub
                        ▼
Orchestrator (FastAPI)
  - Token verify(Firebase) → user_id
  - Routes:
      /ingest/url
      /rag/answer
      /notes
      /graph/view
      /briefings
      /recommendations
      /jobs/* (S2, PKG, Rec 등)
                        ▼
LangGraph (3 major workflows)
  - Ingest / S1 / S2 / PKG
  - RAG Query
  - Weekly Recommendations
                        ▼
Supabase
  - Persistent memory, LTM, PKG, recommendations
```

---

## 7. User Capability Summary

| Category | What User Does | Result |
|----------|----------------|--------|
| Add content | 기사/논문/블로그/PDF 공유 | S1 summary + memory/LTM 저장 |
| Read feed | 요약 피드 보기 | 빠른 TL;DR / bullets 확인 |
| Take notes | 하이라이트, 메모 작성 | notes로 저장, S2에 반영 |
| Ask questions | 자연어 질의 | RAG 기반 answer + citations |
| View mind map | 개념/관계 탐색 | PKG 기반 그래프 뷰 |
| Weekly briefing | 주간 토픽 요약 보기 | S2 기반 consolidated summary |
| Weekly recommendations | Top-3 최신 article/paper 확인 | 개인화된 discovery |
| Provide feedback | up/down/save/dismiss | 추천 가중치 튜닝에 사용 |

---

## 8. 8-Week Development Plan (with Cursor)

### Week 1 – 환경 세팅 & 최소 백엔드 뼈대

**목표**  
Supabase, FastAPI + LangGraph 기본 프로젝트, Firebase 연동 골격까지.

**할 일**  
- Supabase 프로젝트 생성, pgvector enable, 핵심 테이블(sources/chunks/embeddings/summaries/notes) 생성  
- `orchestrator/` 리포지토리 생성 (GitHub + Cursor)  
- FastAPI `/health` 엔드포인트, 기본 구조 생성  
- LangGraph `AgentState` 정의 + 간단 echo 그래프 1개 테스트  
- Firebase Admin 설정 + `verify_id_token` 유틸 추가

**Done 기준**  
- 로컬에서 `uvicorn app.main:app` 실행  
- `/health` 정상 응답  
- Supabase 콘솔에서 테이블 확인 가능  

**Cursor 활용 포인트**  
- FastAPI + LangGraph boilerplate 코드 자동 생성  
- Supabase schema용 SQL 초안 생성 요청  
- AgentState/StateGraph 템플릿 코드 생성


### Week 2 – Ingest + S1 Summarization 최소 구현

**목표**  
`/ingest/url` → Supabase에 `sources/chunks/embeddings/summaries(S1)`까지 end-to-end.

**할 일**  
- URL → HTML → main text 파서 구현 (`web_fetch.py`)  
- 텍스트 chunking 함수 (512~768 tokens, overlap 64 정도)  
- OpenAI Embedding/LLM 연동 (요약용 모델 선택)  
- LangGraph Ingest 그래프:  
  - `[Ingest]` → `sources/chunks` insert  
  - `[Chunk&Embed]` → `embeddings` upsert  
  - `[Summarize.S1]` → `summaries(kind='S1')` insert  
- `/ingest/url` 라우터: idToken 검증 → LangGraph 실행 → TL;DR 반환

**Done 기준**  
- `/ingest/url` 호출 시 Supabase에 sources/chunks/embeddings/summaries 레코드 생성  
- 응답 JSON에 TL;DR + bullets 포함  

**Cursor 활용**  
- 각 LangGraph node 함수 시그니처 & wiring 코드 자동 생성  
- supabase repo wrapper 클래스 골격 작성 도움  
- 요약 prompt 초안 생성


### Week 3 – RAG Query + `/rag/answer` 구현

**목표**  
인제스트된 내용 기반 RAG 질의응답 구현.

**할 일**  
- pgvector kNN SQL (`ORDER BY embedding <-> q_vec LIMIT k`) 작성  
- Repo에 `knn_search(user_id, query_vec, k)` 함수 추가  
- LangGraph RAG 그래프:  
  - `[RAG.Query]` (query embedding)  
  - `[VectorSearch]` (pgvector 검색)  
  - `[AnswerWithCitations]` (LLM answer + citations)  
  - `[Evaluate]` (score logging)  
- `/rag/answer` 라우터 구현

**Done 기준**  
- 몇 개 문서 인제스트 후 `/rag/answer` 호출 → 의미 있는 답변 + citations 반환  

**Cursor 활용**  
- pgvector SQL 템플릿 생성  
- Answer-with-citations prompt 자동 제안  
- 그래프 wiring 리팩토링 지원


### Week 4 – S2 Consolidation + PKG v0 (배치 잡)

**목표**  
Daily S2, Weekly PKG 업데이트 최소 버전.

**할 일**  
- Repo에 `fetch_recent_S1`, `fetch_notes`, `fetch_latest_S2` 추가  
- LangGraph `[Consolidate.S2]` 노드: S1 + notes + 이전 S2 → 새 S2 생성  
- `/jobs/consolidate_s2` 라우터 (수동/스케줄용)  
- `concepts/relations` 테이블 생성  
- PKG v0: 간단 키워드/명사 기반 concept 생성 + 기초 relation (공동 출현 등)

**Done 기준**  
- 수동 `/jobs/consolidate_s2` 실행 시 `summaries(scope='topic', kind='S2')` 생성  
- `concepts` 테이블에 일부 개념 노출

**Cursor 활용**  
- S2 consolidation prompt 설계 도움  
- 간단 concept extraction 코드(예: spaCy 기반) 자동 생성  
- job route boilerplate 생성


### Week 5 – Android App v0 (Auth + Feed + RAG)

**목표**  
Android에서 로그인 + 요약 피드 + 질문하기까지 동작.

**할 일**  
- Firebase Auth/Google Sign-In → ID Token 획득  
- Retrofit 인터셉터에 Authorization 헤더 추가  
- `/feed` API (최근 summaries S1 반환) 구현  
- Compose로 Feed 리스트 + 상세 화면 구성  
- 질의 화면에서 `/rag/answer` 호출 및 결과 렌더링

**Done 기준**  
- 실제 디바이스에서 로그인 → Feed → 질문 → 답변 확인 가능  

**Cursor 활용**  
- Retrofit interface/DTO/Compose 화면 템플릿 자동 생성  
- API 응답 모델/에러 처리 코드 제안


### Week 6 – Notes + Mind Map v0

**목표**  
노트 저장 + PKG 기반 Mind Map v0.

**할 일**  
- `/notes` (POST/GET) 라우터 구현 → Supabase `notes` 저장  
- Android에서 Feed item에 “Add Note” / 하이라이트 기능 구현  
- 간단 Next.js + Cytoscape.js Mind Map 페이지: `concepts/relations` 렌더링  
- Android에서 WebView or CustomTab으로 Mind Map 열기  
- S2 consolidation에 notes 반영 로직 연결

**Done 기준**  
- 앱에서 남긴 노트가 Supabase `notes`에 저장  
- Mind Map 페이지에서 내 지식 그래프가 최소한 표시됨  

**Cursor 활용**  
- Next.js + Cytoscape 샘플 페이지 코드 생성  
- `/notes`와 연동하는 Compose UI 초안 생성


### Week 7 – Weekly Recommendations 파이프라인

**목표**  
S2 + concepts 기반 Top-3 추천 계산 및 저장.

**할 일**  
- `candidates`, `recommendations`, `rec_feedback` 테이블 생성  
- WeeklyRec LangGraph 서브그래프:  
  - `[TopicEnumerate]`  
  - `[QueryExpand]`  
  - `[FetchCandidates]` (초기에는 mock 혹은 단일 소스)  
  - `[EmbedScore]` (Rel/New/Qual/Rec 계산)  
  - `[MMR/Dedup]`  
  - `[Persist+Notify]`  
- `/recommendations` GET API 구현

**Done 기준**  
- `/jobs/recommendations/run` 호출 후 `recommendations`에 토픽별 3개 레코드 생성  
- `/recommendations` 호출로 조회 가능  

**Cursor 활용**  
- 점수 계산 함수, MMR 구현 코드 자동 생성  
- WeeklyRec 그래프 wiring 코드 생성


### Week 8 – Android Weekly UI + 모니터링 + 리팩토링

**목표**  
Weekly 추천 UI, 최소 모니터링, 리팩토링.

**할 일**  
- Weekly 탭에서 topic별 Top-3 추천 카드 UI 구현  
- 카드 액션(👍/👎/save/dismiss) → `/recommendations/feedback` 연동  
- Supabase `runs/events` 기반 간단 metric 쿼리 (요청 수, 에러 수, 평균 latency 등)  
- config/prompt 하드코딩 제거, 공용 util 리팩토링  
- “post-MVP backlog” 리스트업

**Done 기준**  
- 폰에서 Weekly Recommendations 화면이 자연스럽게 동작  
- 최소한의 오류/latency를 로그나 쿼리로 확인 가능  

**Cursor 활용**  
- 프로젝트 전역 리팩토링 (공통 util 추출, 타입 정리)  
- “이 세 파일의 중복 로직 helper로 묶어줘” 같은 리팩토링 지시

---

**Version:** v0.4 (full architecture + workflows + 8-week dev plan)
