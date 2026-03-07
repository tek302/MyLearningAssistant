# S2 Consolidation & Weekly Recommendation — 설계 초안

**목표**
- **S2 Consolidation**: 1주일 동안 ingest한 문서들의 **주요 technical points**를 정리해서 보여주기
- **Weekly Recommendation**: 그 다음 읽을 **paper/article** 추천

이 문서는 BE 설계, 로컬 우선 테스트 전략, Android UX 변경을 함께 정리한다.  
**구현 상태·현재 이슈**: `S2_WEEKLY_STATUS_AND_NEXT.md`, `WEEKLY_RECOMMENDATION_PLAN.md` 참고.

---

## 1. S2 Consolidation

### 1.1 사용자 가치
- “이번 주 내가 읽은 것들의 기술 요약”을 한 화면에서 파악
- 문서 단위(S1)가 아니라 **주간·토픽 단위**로 묶어서 핵심 포인트만 제공

### 1.2 데이터 모델 (현재 스키마 활용)

`summaries` 테이블 그대로 사용:
- `scope = 'topic'`, `kind = 'S2'`
- `source_id = NULL` (토픽 단위이므로 단일 doc 아님)
- `tldr`: 해당 토픽 한 줄 요약
- `bullets`: 주요 technical points 리스트 (5~15개)
- `extra`: 메타데이터
  - `topic_name`: 토픽 라벨 (예: "LLM & RAG", "Compiler Design")
  - `week_start`: 해당 주 시작일 (ISO date, 예: "2025-02-24")
  - `source_ids`: 이 토픽에 기여한 문서 id 배열 (선택)

토픽 구분 방식 (선택지):
- **A) 자동 클러스터링**: 최근 7일 S1들 embedding으로 클러스터링 → 클러스터당 S2 1개
- **B) 단일 “이번 주” S2**: 7일 S1을 한 덩어리로 보고 S2 1개만 생성 (가장 단순)
- **C) 고정/사용자 토픽**: 나중에 topic 테이블 추가 시 확장

**MVP에서는 B로 시작 권장** → 구현 단순, “이번 주 technical points”만 있어도 목표 충족.

### 1.3 Backend

#### 1.3.1 S2 배치 로직 (핵심)
- **입력**: `user_id`, `week_start` (또는 “최근 7일” 계산)
- **단계**:
  1. 해당 user의 `created_at`이 최근 7일 이내인 `sources` 조회
  2. 각 source에 대한 S1 요약 조회 (`summaries.scope='doc' AND kind='S1'`)
  3. S1들의 tldr + bullets를 합친 텍스트로 **LLM 한 번 호출** → “이번 주 주요 technical points” 요약 (tldr + bullets)
  4. `summaries`에 INSERT: `scope='topic'`, `kind='S2'`, `source_id=NULL`, `extra.week_start`, `extra.topic_name='This Week'` (또는 B 시절에는 topic_name 생략 가능)
- **Idempotent**: 같은 `user_id` + `week_start`에 대해 기존 S2가 있으면 **삭제 후 재생성** 또는 **UPDATE** (한 유저당 주당 S2 1개라면 replace)

#### 1.3.2 트리거
- **POST /jobs/s2** (새 API): body에 `{ "week_start": "2025-02-24" }` (optional). 없으면 “이번 주”로 계산.
  - DB에 job 생성: `job_type = 's2'`, `source_id = NULL`, payload는 `extra` 또는 별도 컬럼에 `week_start` 저장 가능.
- **Worker 확장**: `process_job()`에서 `job_type == 's2'`면 S2 배치 함수 호출 (동기 또는 asyncio.to_thread).
- **스케줄**: Cloud Scheduler로 매주 월요일 새벽에 `POST /jobs/s2` 호출하거나, “Process”와 별도로 “주간 요약 생성” 버튼으로 수동 호출 가능.

#### 1.3.3 조회 API
- **GET /s2** 또는 **GET /documents/s2** (기존 feed와 구분):
  - Query: `week_start` (optional), `limit`
  - 응답: `{ "summaries": [ { "id", "tldr", "bullets", "extra": { "week_start", "topic_name" }, "created_at" } ] }`
- 앱에서는 “이번 주” 기본값으로 호출하면 됨.

### 1.4 테스트 (로컬 우선)

- **단위 테스트 (pytest)**  
  - **S2 생성 함수만** 테스트:  
    - Mock DB: “최근 7일” S1 3개 반환하도록 patch → LLM mock해서 고정 문자열 반환 → `insert_summary` 호출 인자 검증 (scope=topic, kind=S2, bullets 개수 등).
  - 로컬에서 **실 DB 없이** 돌리려면 repo를 인터페이스로 두고 MockRepo 주입.
- **통합 테스트 (로컬 DB)**  
  - 테스트용 DB에 user 1명, source 2~3개, S1 요약 넣어 둔 뒤 S2 배치 실행 → `summaries`에 S2 row 1개 생기는지 확인.
- **E2E**  
  - `POST /jobs/s2` → `GET /ingest/status` 또는 job 완료 대기 → `GET /s2` 로 해당 주 S2가 나오는지 확인 (선택).

---

## 2. Weekly Recommendation

### 2.1 사용자 가치
- S2로 정리된 “이번 주 technical points”를 바탕으로 **다음에 읽을 paper/article** 추천
- 토픽별로 Top-N개씩 보여주면 됨 (MVP에서는 N=3).

### 2.2 데이터 모델 (신규 테이블 제안)

MVP에서 최소한으로:

```sql
-- recommendations: 주간 추천 결과 (topic당 Top-N 저장)
create table if not exists recommendations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  topic_name text not null,
  week_start date not null,
  title text not null,
  url text,
  source text,           -- e.g. "arXiv", "ACM"
  score float,
  extra jsonb,           -- published_at, summary_snippet, etc.
  created_at timestamptz default now()
);
create index idx_recommendations_user_week on recommendations(user_id, week_start desc);
```

- **candidates** 테이블은 “후보 수집 단계”용으로 나중에 넣어도 됨. MVP에서는 후보는 메모리에서만 처리하고, 최종 Top-N만 `recommendations`에 저장해도 충분.

### 2.3 Backend

#### 2.3.1 파이프라인 개요
1. **S2 토픽 열거**: 해당 주 S2 요약 조회 (tldr + bullets) → “토픽”이 한 개(이번 주 전체)라면 그 1개만 사용.
2. **쿼리 확장**: S2 텍스트에서 키워드/구문 추출 또는 LLM으로 검색 쿼리 2~3개 생성.
3. **후보 수집**:  
   - **로컬/테스트**: 고정 JSON 파일 또는 mock (arXiv API 호출 스킵).  
   - **실서비스**: arXiv API, RSS, 또는 검색 API로 후보 목록 수집.
4. **Embed + 점수**: 후보 제목+요약을 embed하고, S2 embedding과 유사도 또는 LLM judge로 relevance 점수 부여.
5. **Topic당 Top-3 선정** 후 `recommendations` 테이블에 저장 (같은 user_id, week_start면 기존 삭제 후 insert).

#### 2.3.2 트리거
- **POST /jobs/recommendations**: `week_start` (optional) 받아서 위 파이프라인 실행.
  - Job 타입: `job_type = 'recommendations'`, source_id 없음, payload에 week_start.
- Worker에서 `job_type == 'recommendations'` 처리 → 추천 파이프라인 실행.

#### 2.3.3 조회 API
- **GET /recommendations**: Query `week_start` (optional), `topic_name` (optional).
  - 응답: `{ "recommendations": [ { "id", "topic_name", "title", "url", "source", "score", "week_start", ... } ] }`
- Android는 이 API로 실데이터 연동.

### 2.4 테스트 (로컬 우선)

- **단위**  
  - 후보 수집 단계를 **Mock** (고정 5개 후보 반환) → embed+점수+Top-3 선택 로직만 테스트.  
  - LLM/embedding 호출은 mock.
- **로컬 통합**  
  - Mock 후보 + 실 DB: S2 1개 넣어 두고 추천 job 실행 → `recommendations`에 3건 들어오는지 확인.
- **로컬에서 arXiv 미사용**  
  - 환경변수 `RECOMMENDATIONS_USE_MOCK=true` 면 후보를 항상 mock 데이터로 채우면, 로컬에서 API 키 없이 전체 플로우 검증 가능.

---

## 3. Android UX 제안

### 3.1 S2 (이번 주 technical points) 노출

- **옵션 A — Feed 상단 섹션**  
  - Feed 첫 화면 상단에 “이번 주 요약” 카드 1개: tldr + bullets (접기/펼치기).  
  - 아래는 기존 문서 리스트.  
  - 별도 탭 없이 한 화면에서 “요약 → 문서” 흐름 유지.
- **옵션 B — 별도 탭 “Weekly Summary”**  
  - 하단에 “Weekly Summary” 탭 추가 → 해당 주 S2만 전용 화면에 표시.  
  - 주 선택(이번 주 / 지난주) 드롭다운 가능.
- **옵션 C — Recommendations와 합치기**  
  - “Recommendations” 탭을 “주간 요약 & 추천”으로 변경: 상단에 S2 카드, 하단에 추천 리스트.  
  - 한 탭에서 “이번 주 정리 → 다음 읽을 것”까지 이어지는 UX.

**권장**: **옵션 C**. 기존 Recommendations 탭이 이미 있고, S2와 추천이 개념적으로 연결되므로, 한 화면에서 “이번 주 포인트 + 다음 읽을 것” 순서로 보여주는 것이 자연스러움.

### 3.2 Weekly Recommendation 노출

- 기존 **RecommendationsScreen** 유지하되, **FakeRepository 대신 API 연동**.
  - **GET /recommendations** 호출 (기본: 이번 주).
  - Time Range: “This Week” / “Last Week” (또는 “This Month” → week_start 기반으로 변경).
  - Topic 필터: API가 `topic_name`을 주면 그대로 칩으로 표시 (All + 토픽별).
- **RecommendationCard**  
  - 기존 구조 유지: title, source, date, score.  
  - “Save” 클릭 시 → 해당 URL을 **POST /ingest**로 넣어서 나중에 읽기 큐에 넣는 식으로 확장 가능 (선택).
- **로딩/에러**  
  - S2·추천 모두 아직 없으면 “이번 주 요약을 생성해 보세요” + (선택) “생성” 버튼 → `POST /jobs/s2` 호출.

### 3.3 정리 (UX 변경 포인트)

| 항목 | 변경 |
|------|------|
| S2 | “주간 요약” 카드로 노출 (Recommendations 탭 상단 또는 Feed 상단) |
| Recommendations | Fake → **GET /recommendations** 실데이터, Time range = 주 단위 |
| 탭 구조 | 현재 유지 또는 Recommendations를 “주간 요약 & 추천”으로 라벨만 변경 |
| 주간 요약 생성 | 수동 버튼 또는 백그라운드 job 완료 후 자동 표시 |

---

## 4. API 요약 (Canonical)

| 메서드 | 경로 | 용도 |
|--------|------|------|
| POST | /jobs/s2 | S2 배치 트리거 (body: optional week_start) |
| GET | /s2 또는 /documents/s2 | 해당 주 S2 요약 목록 조회 |
| POST | /jobs/recommendations | 주간 추천 배치 트리거 |
| GET | /recommendations | 추천 목록 조회 (query: week_start, topic_name) |

Job 완료 확인은 기존 **GET /ingest/status?job_id=...** 재사용 (job_type만 s2 / recommendations로 구분).

---

## 5. 로컬 우선 테스트 체크리스트

- [ ] S2 생성 함수 단위 테스트 (mock repo + mock LLM)
- [ ] S2 통합: 로컬 DB + S1 2~3개 → S2 1개 생성 검증
- [ ] 추천 파이프라인: 후보 mock → Top-3 저장 검증
- [ ] `RECOMMENDATIONS_USE_MOCK=true` 로 전체 플로우 로컬 실행
- [ ] Android: Mock API 또는 로컬 BE로 Recommendations 화면 실데이터 바인딩
- [ ] (선택) E2E: POST /jobs/s2 → GET /s2, POST /jobs/recommendations → GET /recommendations

---

## 6. 다음 단계

1. **BE**: S2 배치 함수 + `POST /jobs/s2`, `GET /s2` 구현 및 job_runner에 s2 처리 추가.
2. **BE**: `recommendations` 테이블 마이그레이션, 추천 파이프라인 (mock 후보 옵션 포함), `POST /jobs/recommendations`, `GET /recommendations` 구현.
3. **Test**: 위 체크리스트대로 pytest + 로컬 DB 테스트 추가.
4. **Android**: GET /s2, GET /recommendations API 클라이언트 추가 → Recommendations 탭을 “주간 요약 + 추천”으로 변경, Fake 제거.

이 설계로 구현 순서와 계약(API, 스키마)이 정리되므로, 단계별로 적용하면 된다.
