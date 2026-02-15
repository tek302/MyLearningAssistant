# 🚀 MVP Plan — Firebase Gateway + LangChain Orchestrator + Supabase (pgvector)

**Version:** 0.1  
**Goal:** Android에서 관심 토픽을 인제스트→RAG 요약→피드/브리핑 제공.  
**Stack:** Firebase (Functions/FCM) + External Orchestrator (FastAPI + LangChain/LangGraph) + Supabase (Postgres + pgvector + Storage).

---

## 0) 아키텍처 개요

```
Android App
  ├─ Sign-in (Firebase Auth) / Retrofit / FCM
  └─ Screens: Feed, Detail, Highlights, Settings

Firebase (Gateway)
  ├─ Cloud Functions (HTTP): /ingest, /feed, /notify
  ├─ Scheduler + Pub/Sub: periodic fetch jobs
  ├─ Firestore (lightweight cache: read markers, last_seen, device tokens)
  └─ FCM: push notifications

Orchestrator Service (Cloud Run / Render / VM)
  ├─ FastAPI + LangChain/LangGraph (Plan→Search→Evaluate→Refine→Synthesize)
  ├─ Tools: web fetcher, parser, embedding, summarizer, grader
  ├─ Supabase Client: Postgres(pgvector), Storage
  └─ Checkpoint/Logs: Supabase tables (runs, checkpoints, events)

Supabase
  ├─ Postgres + pgvector: sources, chunks, embeddings, notes, concepts, relations
  └─ Storage: raw documents (PDF/HTML snapshots), thumbnails
```

**Identity:** Firebase ID 토큰을 Orchestrator에서 검증(verifyIdToken) → `users.firebase_uid`로 매핑.  
**RBAC:** 기본은 per-user row-level policy (RLS) — Supabase 정책으로 강제.

---

## 1) 코드 구조 (Mono-repo 권장)

```
mvp/
├─ android-app/
│   ├─ app/src/main/java/com/example/app/...
│   ├─ data/ (Retrofit, models, repos)
│   ├─ ui/ (Compose screens)
│   └─ build.gradle.kts
│
├─ firebase-gateway/
│   ├─ functions/
│   │   ├─ src/
│   │   │   ├─ ingest.ts          # POST /ingest  (URL, topic → orchestrator)
│   │   │   ├─ feed.ts            # GET  /feed    (Supabase 조회 프록시, 캐시)
│   │   │   ├─ notify.ts          # POST /notify  (FCM push helper)
│   │   │   ├─ hooks.ts           # Scheduler / PubSub handlers
│   │   │   └─ common/
│   │   │       ├─ auth.ts        # Firebase token verify + claims
│   │   │       ├─ http.ts        # axios wrapper (orchestrator endpoint)
│   │   │       └─ types.ts       # zod schemas (request/response)
│   │   ├─ package.json
│   │   └─ tsconfig.json
│   └─ firestore.rules
│
├─ orchestrator/
│   ├─ app/
│   │   ├─ main.py                 # FastAPI entry (health, /rag/answer, /ingest/url)
│   │   ├─ deps.py                 # auth (verify firebase token), db clients
│   │   ├─ chains/
│   │   │   ├─ planner.py
│   │   │   ├─ searcher.py
│   │   │   ├─ evaluator.py
│   │   │   ├─ refiner.py
│   │   │   └─ synthesizer.py
│   │   ├─ tools/
│   │   │   ├─ web_fetch.py        # Requests + Readability, robots handling
│   │   │   ├─ embed.py            # OpenAI embedding
│   │   │   ├─ summarize.py        # LLM summarizer with citations
│   │   │   └─ supabase_io.py      # SQL/Storage helpers
│   │   ├─ storage/
│   │   │   ├─ schema.py           # pydantic models
│   │   │   ├─ queries.sql         # parametrized SQL
│   │   │   └─ migrations/         # alembic-like SQL files (optional)
│   │   ├─ eval/
│   │   │   └─ rubric.py           # faithfulness/coverage/recency grading
│   │   └─ telemetry/
│   │       ├─ logger.py           # structured logs
│   │       └─ tracing.py          # OpenTelemetry (optional)
│   ├─ requirements.txt
│   └─ Dockerfile
│
└─ supabase/
    ├─ sql/00_enable_extensions.sql
    ├─ sql/10_schema_core.sql
    ├─ sql/20_indexes.sql
    ├─ sql/30_policies.sql
    └─ README.md
```

**CI/CD**  
- GitHub Actions:  
  - `firebase-hosting-merge.yml` — Functions 배포  
  - `orchestrator-build-deploy.yml` — Docker build → Cloud Run/Render 배포  
  - `supabase-migrate.yml` — SQL 적용 (change set 번호 기반)

---

## 2) Supabase 스키마 (핵심)

`sql/00_enable_extensions.sql`
```sql
create extension if not exists vector;
create extension if not exists pgcrypto;
```

`sql/10_schema_core.sql`
```sql
-- users (firebase_uid로 매핑)
create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  firebase_uid text unique not null,
  email text,
  display_name text,
  created_at timestamptz default now()
);

-- sources: 기사/논문/웹 문서
create table if not exists sources (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  url text,
  title text,
  authors text[],
  published_at timestamptz,
  lang text,
  meta jsonb,
  hash text unique,
  created_at timestamptz default now()
);

-- chunks & embeddings
create table if not exists chunks (
  id uuid primary key default gen_random_uuid(),
  source_id uuid references sources(id) on delete cascade,
  ord int,
  text text
);

create table if not exists embeddings (
  chunk_id uuid primary key references chunks(id) on delete cascade,
  embedding vector(1536)
);

-- indexing for vector search
create index if not exists idx_embeddings_cosine
  on embeddings using ivfflat (embedding vector_cosine_ops);

-- topic mapping (선택)
create table if not exists source_topics (
  source_id uuid references sources(id) on delete cascade,
  topic text,
  score real,
  primary key (source_id, topic)
);

-- notes/highlights
create table if not exists notes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  source_id uuid references sources(id) on delete cascade,
  selection text,
  note text,
  tags text[],
  created_at timestamptz default now()
);

-- personal knowledge graph
create table if not exists concepts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  name text,
  aliases text[],
  description text,
  importance real default 0,
  embedding vector(1536),
  created_at timestamptz default now()
);

create table if not exists relations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  src uuid references concepts(id) on delete cascade,
  dst uuid references concepts(id) on delete cascade,
  type text check (type in ('prereq','part_of','supports','contrasts','derived_from')),
  weight real,
  evidence jsonb,
  created_at timestamptz default now()
);

-- runs/checkpoints/events: agent 실행 추적
create table if not exists runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  kind text,                 -- ingest, rag_answer, briefing
  status text,               -- queued, running, done, failed
  score real,
  total_tokens int,
  cost_usd numeric(10,4),
  started_at timestamptz default now(),
  ended_at timestamptz
);

create table if not exists checkpoints (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references runs(id) on delete cascade,
  node text,
  state_json jsonb,
  created_at timestamptz default now()
);

create table if not exists events (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references runs(id) on delete cascade,
  node text,
  level text,             -- info, warn, error
  message text,
  payload jsonb,
  created_at timestamptz default now()
);
```

`sql/30_policies.sql` (개요 – 실제 배포 시 RLS ON)
```sql
alter table users enable row level security;
create policy "own-user" on users
  for select using (firebase_uid = current_setting('request.jwt.claims', true)::json->>'sub');

-- 각 테이블에 대해 user_id로 소유권 제한 정책 추가 (생략 부분 배포 시 작성)
```

---

## 3) API 계약 (초안)

**Firebase Functions (게이트웨이)**  
- `POST /ingest` — body: `{ url, topic? }` → Orchestrator `/ingest/url`로 위임, 결과 `source_id` 반환  
- `GET /feed?topic=&limit=` — Supabase에서 최근 요약/중요도 기준 리스트 반환  
- `POST /notify` — body: `{ userId, title, body, sourceId }` → FCM 전송

**Orchestrator (FastAPI)**  
- `POST /ingest/url` — {url, topic?} → fetch/parse → chunks/embeddings/sources 저장  
- `POST /rag/answer` — {query, topic?, k?, with_citations?} → {answer, citations[]}  
- `GET /briefings?range=weekly` — 개인화 브리핑 생성/조회  
- `POST /notes` — 하이라이트/메모 저장  
- `GET /graph/view?topic=&since=` — 마인드맵 노드/엣지 JSON

**인증:** 모든 요청은 Firebase ID 토큰 헤더(`Authorization: Bearer <idToken>`) 필수. Orchestrator에서 검증 후 `users` 매핑.

---

## 4) 프롬프트/체인 버저닝

- `orchestrator/prompts/summary_v1.md`, `planner_v1.md`, `grader_v1.md`
- 실행 시 각 프롬프트 SHA 해시를 `runs`/`events`에 기록 → 재현 가능성 확보
- LangGraph 노드별 timeouts/retries/token caps 설정

---

## 5) 9주 개발 계획 (Milestone 기반)

### W1 — 프로젝트 부팅 & 기반 설정
- [ ] Repo 생성 (mono-repo), 기본 README
- [ ] Firebase 프로젝트/Functions 2세대 초기화, FCM 세팅
- [ ] Supabase 프로젝트 생성, 확장/스키마 적용(pgvector)
- [ ] Orchestrator FastAPI 스캐폴딩 (health, auth verify)

**Exit:** `/health` OK, Supabase 연결 OK, Android 샘플 앱 빌드 OK

---

### W2 — Ingest 파이프라인 (URL → 소스 저장)
- [ ] Orchestrator: `/ingest/url` (fetch → parse → normalize → chunks)
- [ ] Embedding 저장(embeddings), hash 중복 방지
- [ ] Firebase `/ingest` → Orchestrator 프록시 구현
- [ ] 간단 Admin CLI: `python -m ingest <url>`

**Exit:** 특정 URL 인제스트 후 Supabase에 `sources/chunks/embeddings` 저장 확인

---

### W3 — RAG 검색 & 요약(초안)
- [ ] `/rag/answer` — query embed → k-NN retrieve → synthesis
- [ ] 인라인 인용(citations: source_id, chunk ord) 포함
- [ ] Android: Feed 화면 스켈레톤, Retrofit 연결

**Exit:** 앱에서 질의 → 답변+근거가 JSON으로 수신

---

### W4 — 주기 수집 & 푸시 알림
- [ ] Firebase Scheduler→Pub/Sub→/ingest 배치
- [ ] 중요도 스코어(신규/인용/사용자 태그)로 feed 정렬
- [ ] /notify 함수 및 앱 FCM 수신 처리

**Exit:** 스케줄 실행 → 신규 요약 푸시 수신

---

### W5 — 평가(Evaluator) & 재질의(Refiner) 루프
- [ ] LangGraph 구성: `planner → searcher → evaluator → (refiner?) → synthesizer`
- [ ] 루브릭: faithfulness/coverage/recency, score<0.75이면 재탐색
- [ ] runs/checkpoints/events 기록

**Exit:** 스코어가 낮은 케이스에서 자동 재탐색 후 개선된 답변 생성

---

### W6 — 개인 메모/하이라이트 + Learn Pack v0
- [ ] `/notes` 저장 + Feed 상세에서 하이라이트 생성
- [ ] Learn Pack(요약, 개념 키카드, 퀴즈 3문항) JSON 생성
- [ ] Storage에 썸네일/스냅샷 저장

**Exit:** 한 문서에서 하이라이트→Learn Pack 표시

---

### W7 — 개인 지식 그래프 v0 & Mind Map(웹) MVP
- [ ] 개념 추출(간단 키프레이즈/NER) → `concepts/relations` 기입
- [ ] Next.js + Cytoscape.js로 시각화 (토픽/기간 필터, k-hop)
- [ ] Export(PNG/SVG), 공유 링크(토큰)

**Exit:** 웹에서 개인 Mind Map 가시화 가능

---

### W8 — 품질/관측/비용 관리
- [ ] OpenTelemetry/구조 로그 → Dashboard(예: Grafana, Metabase)
- [ ] 토큰/지연/성공률/스코어 월간 리포트
- [ ] 프롬프트 버전 롤아웃 가드(퍼센트 롤아웃)

**Exit:** 대시보드에서 핵심 지표 확인, 리그레션 20 케이스 통과

---

### W9 — 경량 보안/정책 & 베타 릴리스
- [ ] Supabase RLS/정책 정리, 최소권한 서비스 계정
- [ ] 에러/재시도 정책, DLQ 운용
- [ ] 베타 사용자 온보딩(내부 5–10명)

**Exit:** 베타 배포, 피드백 수집 루프 가동

---

## 6) 환경변수(.env 예시)

**firebase-gateway/.env**
```
ORCHESTRATOR_URL=https://orchestrator.example.com
FIREBASE_PROJECT_ID=...
OPENAI_API_KEY=sm://projects/.../secrets/...  # Secret Manager 경유 권장
```

**orchestrator/.env**
```
OPENAI_API_KEY=...
SUPABASE_URL=...
SUPABASE_SERVICE_KEY=...
JWT_AUDIENCE=firebase
ALLOWED_ORIGINS=https://app.example.com
```

---

## 7) 개발 가드레일

- **Idempotency:** `hash(url+title)`로 중복 인제스트 방지
- **토큰 가드:** 입력 토큰 상한, 요약 길이 제한
- **비용 가드:** 모델/온도/맥스토큰 노드별 상한
- **관측:** 노드별 p95, 토큰/비용 분리 로깅
- **프롬프트 버전관리:** 파일/해시 기록, 점진적 롤아웃
- **테스트:** 20개 리그레션 질의 셋(정답·근거·스코어 기준)

---

## 8) Android 연동 포인트(간단 예시)

```kotlin
interface Api {
  @POST("ingest")
  suspend fun ingest(@Body req: IngestReq): IngestResp

  @GET("feed")
  suspend fun feed(@Query("topic") topic: String, @Query("limit") limit: Int = 20): List<FeedItem>
}
```

- FCM 토큰 등록: 로그인 직후 Functions `/notify/register`(옵션)  
- 백그라운드 동기화: WorkManager(Y-nightly + Wi-Fi)

---

## 9) 데모 체크리스트 (주차별 완료 기준)
- [ ] 특정 URL 인제스트 → 앱 피드에 요약 노출
- [ ] RAG 질의 → 인라인 인용 포함 답변 표시
- [ ] 스케줄러에 의해 자동 인제스트/푸시
- [ ] 평가/재질의 루프가 낮은 점수를 개선
- [ ] 하이라이트→Learn Pack 생성
- [ ] Mind Map 웹으로 가시화/Export
- [ ] 대시보드에서 토큰/지연/성공률 확인
- [ ] 베타 릴리스(내부 사용자)

---

### 부록 A — 최소 요약 프롬프트 (예시)

```
You are a technical editor for {topic}.
Summarize the retrieved chunks with strict grounding.
Return JSON: { "tldr": string(≤2 lines), "bullets": string[5], "actions": string[3] }.
Include inline citations as [S{source_id}#C{chunk_ord}]. Avoid speculation.
```

### 부록 B — 평가 루브릭 (예시)
- **Faithfulness:** 근거 청크와 모순 없음(0–1)  
- **Coverage:** 질의 요구 범위 커버(0–1)  
- **Recency:** 최신 출처 가중(0–1)  
- **Specificity:** 수치/식/구체 사례 포함(0–1)

점수 < 0.75 → `Refiner`가 재질의/재검색 후 재시도.

---

**문의/변경**: 주간 플래닝 전 문서 업데이트(버전 태그 `v0.1.x`).  
다음 단계로 *어느 파트부터 코드 스캐폴딩을 받을지* 알려주세요.
