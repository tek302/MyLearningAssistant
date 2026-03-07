# Weekly Recommendation — Usage Flow & 구현 계획

**기준**: S2 생성 시 Top 3 arXiv 추천 생성, 추천은 title+abstract만 저장, Feed는 누적·Process 시 Ingest+삭제·명시적 삭제 지원.

---

## 구현 상태 (Status) — 2026-03

| 구분 | 상태 | 비고 |
|------|------|------|
| **DB** | ✅ 완료 | `sql/52_schema_recommendations.sql` 적용. `recommendations` 테이블·인덱스 |
| **BE 추천 생성** | ✅ 완료 | `arxiv_recommendations.py`: S2 텍스트→검색 쿼리→arXiv API→S2 embedding re-rank→Top 3 INSERT. S2 job 성공 직후 호출, 실패 시 job은 성공 유지·`recommendations_failed` 플래그 |
| **BE API** | ✅ 완료 | GET /recommendations (week_start, topic_name, limit), DELETE /recommendations/{id} |
| **Android** | ✅ 완료 | Recommendations 탭 실데이터 연동. 카드(title, abstract, 원문 링크), Process(ingest 후 삭제), Remove(삭제만), Time range·Topic 필터 |
| **로컬 테스트** | ✅ 가능 | §9 및 `S2_LOCAL_TEST.md` 참고. uvicorn + API 호출·실기기 Cloud 연동 확인됨 |

**MVP 대비**: `MVP_v1.2_CROSSCHECK.md` §1·§2 참고. Week 9 Weekly Recommendation 완료로 반영됨.

---

## 1. Usage Flow (요청하신 대로)

| 단계 | 동작 |
|------|------|
| **1) S2 생성 시** | S2 summary를 만들 때 **동시에** 해당 주 기준 Top 3 arXiv 논문 추천을 생성해 `recommendations` 테이블에 저장. (별도 job이 아니라 **S2 job 한 번**에 S2 + 추천까지 수행) |
| **2) 추천 데이터** | **DB에 ingest 하지 않음.** arXiv API에서 **title + abstract**만 가져와서 `recommendations` 행으로만 저장. PDF/본문은 사용자가 "Process"할 때만 ingest. |
| **3) Recommendation Feed** | 주간 Top 3가 **리스트에 계속 쌓임** (매 주 새 3개 추가, 기존 건 삭제하지 않음). |
| **4) Process** | 사용자가 추천 항목에서 **Process** 선택 → 해당 논문을 **Ingest** (POST /ingest, arXiv PDF URL) → 처리 시작 후 **해당 추천을 recommendation 리스트에서 삭제**. |
| **5) 명시적 삭제** | Ingest 없이 리스트에서만 제거하는 **삭제 버튼** 제공 (DELETE). |

---

## 2. 가능 여부 검토

### 2.1 S2 생성 시 동시에 Top 3 추천 생성

- **가능.**  
  - 현재: `run_s2_consolidation()` 성공 시 S2만 저장하고 끝.  
  - 변경: S2 저장 직후 같은 `user_id`, `week_start`로 **arXiv 기반 추천 생성 함수** 호출 → Top 3 결과를 `recommendations`에 INSERT.  
  - 별도 job 타입 없이 **S2 job 한 번**에 S2 + 추천까지 수행하도록 하면 됨.

### 2.2 추천 = title + abstract만, DB ingest 없음

- **가능.**  
  - **arXiv API**: `https://export.arxiv.org/api/query?search_query=...&max_results=N`  
    - 응답: Atom XML. 각 `<entry>`에 `<title>`, `<summary>`(abstract), `<id>`(arxiv id), `<link>`(abs/pdf) 포함.  
    - PDF 다운로드 없이 **메타데이터만** 조회 가능.  
  - **원문 링크**: API 응답의 `<link href="...">`(abstract 페이지, 예: `https://arxiv.org/abs/1234.56789`)를 `url` 컬럼에 저장. 추천 카드에 **원문 링크**로 표기해 사용자가 클릭해 논문 페이지로 이동할 수 있게 함. Process 시에는 이 `url`을 그대로 POST /ingest에 넘기면 되며, 백엔드에서 이미 abs → pdf 변환 지원.
  - 프로젝트에서 이미 `run_pdf_worker` 등에서 `ARXIV_API_URL` + `id_list`로 제목 조회 중. 동일 API에 `search_query`를 넣어 검색하면 여러 논문의 title/summary/link를 한 번에 가져올 수 있음.  
  - 따라서 **title + abstract + 원문 link**만 가져와서 `recommendations` 행으로 저장하고, **sources/chunks에는 넣지 않음.**  
  - 사용자가 "Process"할 때만 그때 해당 arXiv URL로 POST /ingest 호출.

### 2.3 Recommendation Feed 누적 + Process 시 Ingest 후 삭제 + 명시적 삭제

- **가능.**  
  - **누적**: 주마다 Top 3를 **INSERT만** 하고, 기존 추천을 지우지 않음. GET /recommendations는 해당 user의 전체 추천을 (예: 최신순) 반환.  
  - **Process**:  
    - 앱에서 해당 추천의 `url`(arXiv PDF URL)로 **POST /ingest** 호출 → job_id 수신.  
    - 이어서 **DELETE /recommendations/{id}** 호출하여 리스트에서 제거.  
    - (선택) 백엔드에서 **POST /recommendations/{id}/ingest** 하나로 “ingest 트리거 + 해당 추천 삭제”를 묶어도 됨.)  
  - **명시적 삭제**: **DELETE /recommendations/{id}** 한 번으로 리스트에서만 제거 (ingest 없음).

---

## 3. 데이터 모델

- **원문 링크**: arXiv API에서 가져온 abstract 페이지 URL(예: `https://arxiv.org/abs/1234.56789`)을 `url`에 저장. 추천 카드에 **원문 링크**로 표기. Process 시 이 `url`을 POST /ingest에 전달하면 백엔드에서 abs → pdf 변환 후 ingest.

```sql
-- recommendations: 주간 추천 (arXiv title + abstract + 원문 link만 저장, ingest는 Process 시에만)
create table if not exists recommendations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  topic_name text not null,           -- e.g. "This Week"
  week_start date not null,
  title text not null,
  abstract text,                      -- arXiv summary
  url text not null,                  -- 원문 link (arxiv.org/abs/...); 카드에 표기, Process 시 ingest에 사용
  source text not null default 'arXiv',
  score float,
  created_at timestamptz default now()
);
create index idx_recommendations_user_created on recommendations(user_id, created_at desc);
```

- **source_id 없음** → 추천은 항상 “메타데이터만” 저장. 실제 문서는 Process 시 POST /ingest로만 생성.
- **마이그레이션 파일**: `orchestrator/sql/52_schema_recommendations.sql`

---

## 4. Backend 구현 계획

### 4.1 arXiv 검색 + Top 3 생성

- **입력**: `user_id`, `week_start`, S2 텍스트(또는 tldr+bullets).
- **단계**:
  1. S2 텍스트에서 **검색 쿼리** 생성: 키워드 추출 또는 LLM으로 `search_query` 1개 생성 (예: `all:attention+transformer`).
  2. **arXiv API** 호출: `GET https://export.arxiv.org/api/query?search_query=...&max_results=10&sortBy=relevance` (또는 `submittedDate`).
  3. 응답 XML 파싱: 각 entry에서 **title**, **summary**(abstract), **link**(원문 URL: abstract 페이지 `arxiv.org/abs/...` 권장) 추출.
  4. (선택) S2 embedding과 유사도로 re-rank 하거나, 그냥 상위 3개 사용.
  5. **Top 3**를 `recommendations` 테이블에 INSERT (같은 `user_id`+`week_start`라도 **기존 행 삭제하지 않음** → 누적).

- **모듈**: 예) `app/services/recommendation_service.py` 또는 `app/services/arxiv_recommendations.py`.

### 4.2 S2 job 안에서 추천 생성 호출

- **위치**: `run_s2_consolidation()` 끝에서, S2 INSERT 성공 후.
- **로직**: `run_s2_consolidation()`가 성공(True)을 반환하기 직전에, 같은 `user_id`, `week_start`와 방금 만든 S2 텍스트로 **arXiv Top 3 추천 생성** 함수 호출 → `recommendations`에 3건 INSERT.
- **실패 처리**: 추천 생성이 실패해도 S2는 이미 저장됐으므로, 로그만 남기고 S2 job은 성공으로 두어도 됨 (또는 job payload에 `recommendations_failed` 플래그만 넣을지 정책 결정).

### 4.3 API

| 메서드 | 경로 | 용도 |
|--------|------|------|
| GET | /recommendations | 해당 user의 추천 목록 (최신순). Query: `week_start`, `topic_name` (선택), `limit`. |
| DELETE | /recommendations/{id} | 추천 1건 삭제 (리스트에서 제거). 본인 소유만. |
| POST | /recommendations/{id}/ingest | (선택) 해당 추천의 `url`로 ingest job 생성 + 해당 추천 삭제. 응답에 `job_id` 포함. |

- **Process**를 앱에서만 처리할 경우: 앱이 **POST /ingest** 후 **DELETE /recommendations/{id}** 호출하면 됨.  
- **Process**를 백엔드 한 번에 처리하려면 **POST /recommendations/{id}/ingest**를 두어서 내부에서 ingest job 생성 + 추천 삭제.

### 4.4 응답 형식 (GET /recommendations)

- `{ "recommendations": [ { "id", "topic_name", "week_start", "title", "abstract", "url", "source", "score", "created_at" } ] }`  
- Android에서는 이걸로 카드 표시: **title**, **abstract**, **url(원문 링크)**, source. Process 시 `url`로 ingest, 삭제 시 `id`로 DELETE.

---

## 5. Android UX

- **Recommendation Feed**: GET /recommendations로 목록 표시 (최신순 누적).
- **카드**: title, abstract(일부 또는 접기/펼치기), **원문 링크(url)** 표기, source(arXiv), (선택) score.
- **Process 버튼**:  
  - 클릭 시 해당 항목의 `url`로 **POST /ingest** 호출 → (선택) **DELETE /recommendations/{id}** 호출하여 리스트에서 제거.  
  - 또는 **POST /recommendations/{id}/ingest** 사용 시 한 번에 처리.
- **삭제(Remove) 버튼**: **DELETE /recommendations/{id}** 호출만 하여 리스트에서 제거 (ingest 없음).
- Time range 필터(이번 주 / 지난주)는 `week_start` 쿼리로 구현 가능. 토픽 필터는 `topic_name` 쿼리.

---

## 6. 구현 순서 제안

1. **DB**: `recommendations` 테이블 마이그레이션 (위 스키마).
2. **Backend**: arXiv 검색 + Top 3 생성 서비스 (S2 텍스트 → search_query → arXiv API → 파싱 → INSERT 3건).
3. **Backend**: `run_s2_consolidation()` 성공 후 위 서비스 호출하여 해당 주 추천 3건 INSERT.
4. **Backend**: **GET /recommendations**, **DELETE /recommendations/{id}**, (선택) **POST /recommendations/{id}/ingest**.
5. **Android**: Recommendations 화면을 Fake 제거 후 GET /recommendations 연동, Process(ingest 후 삭제), 삭제(Remove) 버튼 연동.

**BE 수정 사항 로컬 테스트**: §9 및 `docs/S2_LOCAL_TEST.md` 참고 (실수·고생했던 점 포함).

---

## 7. 정리

| 요청 | 검토 결과 |
|------|-----------|
| S2 생성 시 Top 3 arXiv 추천 생성 | ✅ S2 job 안에서 S2 저장 직후 추천 생성 함수 호출로 구현 가능. |
| 추천은 title+abstract만, DB ingest 안 함 | ✅ arXiv API로 메타만 조회 가능; recommendations에만 저장. Process 시에만 ingest. |
| 추천 Feed에 계속 쌓이기 | ✅ 주마다 INSERT만 하고 기존 건 삭제하지 않음. |
| Process 선택 시 Ingest + 리스트에서 삭제 | ✅ POST /ingest(url) + DELETE /recommendations/{id} 또는 POST /recommendations/{id}/ingest. |
| 명시적 삭제 버튼 | ✅ DELETE /recommendations/{id} 로 구현. |

이 순서대로 구현하면 요청하신 usage flow에 맞게 동작한다.

---

## 8. Backend 설계 상세

### 8.1 DB 마이그레이션

- **파일**: `orchestrator/sql/52_schema_recommendations.sql`  
- **실행**: Supabase SQL Editor 또는 `psql $SUPABASE_DB_URL -f sql/52_schema_recommendations.sql`  
- **의존성**: `10_schema_core.sql` (users 테이블)

### 8.2 Repo (SupabaseRepo 또는 별도)

- **insert_recommendation**(user_id, topic_name, week_start, title, abstract, url, source, score) → id  
- **list_recommendations**(user_id, week_start=None, topic_name=None, limit=50) → list[dict] (created_at desc)  
- **get_recommendation_by_id**(recommendation_id, user_id) → dict | None (본인 소유만)  
- **delete_recommendation**(recommendation_id, user_id) → bool (삭제된 행 있으면 True)

### 8.3 arXiv 추천 서비스 (신규 모듈)

- **위치**: `app/services/arxiv_recommendations.py` (또는 `recommendation_service.py`)  
- **함수**: `run_arxiv_recommendations_for_week(user_id: str, week_start: str, s2_text: str) -> Tuple[int, Optional[str]]`  
  - **입력**: user_id, week_start(YYYY-MM-DD), s2_text(S2 tldr+bullets 합친 텍스트).  
  - **단계**:  
    1. s2_text에서 arXiv 검색 쿼리 생성: 키워드 추출(간단 규칙) 또는 LLM 1회 호출로 `search_query` 문자열 생성 (예: `all:transformer+attention`).  
    2. `GET https://export.arxiv.org/api/query?search_query=...&max_results=10&sortBy=relevance` 호출.  
    3. Atom XML 파싱: 각 `<entry>`에서 `<title>`, `<summary>`, `<link rel="alternate" href="...">`(또는 abs 링크) 추출. 원문 링크는 abs URL(arxiv.org/abs/...) 우선 저장.  
    4. 상위 3개 선택 (필요 시 재정렬).  
    5. `repo.insert_recommendation(...)` 3회 호출 (topic_name="This Week", source="arXiv").  
  - **반환**: (삽입 건수, None) 또는 (0, error_message).  
  - **실패 시**: 예외 잡아서 로그만 남기고 (0, str(e)) 반환 → S2 job은 성공 유지.

### 8.4 S2 Consolidation 연동

- **파일**: `app/services/s2_consolidation.py`  
- **변경**: `run_s2_consolidation()`에서 S2 INSERT 성공 직후, 같은 `user_id`, `week_start`와 `combined_text`로 `run_arxiv_recommendations_for_week(user_id, week_start, combined_text)` 호출.  
- 반환값은 로그만 남기고 무시 (추천 실패해도 S2는 성공 처리).

### 8.5 API 라우터

- **prefix**: `/recommendations`  
- **GET /**  
  - Query: `week_start` (optional), `topic_name` (optional), `limit` (default 50).  
  - 의존성: `get_user_id`.  
  - 동작: `repo.list_recommendations(user_id, ...)` → `{ "recommendations": [ ... ] }`. 각 항목에 id, topic_name, week_start, title, abstract, url, source, score, created_at.  
- **DELETE /{id}**  
  - Path: recommendation id.  
  - 동작: 본인 소유 확인 후 `repo.delete_recommendation(id, user_id)`. 204 또는 404.  
- **POST /{id}/ingest** (선택)  
  - 동작: `get_recommendation_by_id(id, user_id)` → url로 ingest job 생성 (`_upsert_source_pending` + `create_job`) → `delete_recommendation(id, user_id)` → `{ "job_id": "...", "status": "queued" }`.  
  - 없으면 앱에서 POST /ingest + DELETE /recommendations/{id} 두 번 호출로 동일 동작 가능.

### 8.6 구현 순서 (BE)

1. `sql/52_schema_recommendations.sql` 적용.  
2. Repo에 `insert_recommendation`, `list_recommendations`, `get_recommendation_by_id`, `delete_recommendation` 추가.  
3. `app/services/arxiv_recommendations.py` 구현 (쿼리 생성 → arXiv API → 파싱 → Top 3 INSERT).  
4. `run_s2_consolidation()` 끝에서 `run_arxiv_recommendations_for_week` 호출.  
5. `app/routers/recommendations.py` 추가: GET, DELETE, (선택) POST .../ingest.  
6. `app/main.py`에 router 등록.

---

## 9. BE 로컬 테스트

S2 + 추천(Recommendations) 백엔드 수정 사항을 로컬에서 검증하는 방법입니다.  
**S2 주간 요약 로컬 테스트**는 `docs/S2_LOCAL_TEST.md`를 먼저 참고하고, 아래는 그 위에 Recommendations 관련 단계와 실수하기 쉬운 점을 정리한 것입니다.

### 9.1 참고 문서

- **S2 로컬 테스트**: `orchestrator/docs/S2_LOCAL_TEST.md`  
  - uvicorn 기동, Auth bypass, `POST /jobs/s2` → trigger-worker → `GET /s2` 흐름.  
  - **그때 실수·고생했던 것들**을 그대로 반영했으므로, 아래 “주의사항”과 함께 읽을 것.

### 9.2 사전 준비

- **S2_LOCAL_TEST.md의 사전 준비를 그대로 따릅니다.**  
  - DB: `51_jobs_payload.sql` 적용.  
  - `.env`: `SUPABASE_DB_URL`, `OPENAI_API_KEY`, `APP_ENV=local`, `AUTH_BYPASS_USER_ID` (테스트할 유저).  
  - Firebase 자격 증명 비우면 auth bypass.
- **Recommendations용 추가 마이그레이션**  
  - `orchestrator/sql/52_schema_recommendations.sql`을 Supabase SQL Editor 또는 psql로 실행.  
  - 적용 전에 `recommendations` 테이블이 있으면 스키마 오류가 날 수 있으므로, 한 번만 실행.
- **추천 생성에 필요한 것**  
  - S2 job 성공 후 같은 `user_id`·`week_start`로 추천이 돌므로, **S2가 생성될 수 있는 유저**가 필요함 (최근 7일 소스 + S1 요약 존재).  
  - 임베딩 사용 시: `OPENAI_API_KEY` 등 해당 서비스 키가 .env에 있어야 re-rank/추천 생성이 실패하지 않음.

### 9.3 로컬 테스트 순서 (방법 A: uvicorn + API)

1. **uvicorn 기동**  
   ```powershell
   cd orchestrator
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
2. **유저 확인 (실수 방지)**  
   ```powershell
   Invoke-RestMethod -Uri "http://localhost:8000/me"
   ```  
   - `resolved_user_id`가 DB의 테스트 유저 UUID와 일치하는지 확인.  
   - **.env의 `AUTH_BYPASS_USER_ID`를 바꾼 뒤에는 반드시 uvicorn 재시작** (S2_LOCAL_TEST에서 강조한 내용).
3. **S2 job 넣기**  
   ```powershell
   Invoke-RestMethod -Method Post -Uri "http://localhost:8000/jobs/s2" -ContentType "application/json" -Body "{}"
   ```  
   필요 시: `'{"week_start": "2026-03-03"}'` 등으로 지정.
4. **한 건 처리 (worker tick)**  
   ```powershell
   Invoke-RestMethod -Method Post -Uri "http://localhost:8000/me/trigger-worker"
   ```  
   - S2 consolidation 성공 후 같은 run에서 **arXiv 추천 생성**이 호출됨.  
   - 추천 생성이 실패해도 job은 성공으로 남고, job payload에 `recommendations_failed: true`만 세팅됨.
5. **S2 결과 확인**  
   ```powershell
   Invoke-RestMethod -Uri "http://localhost:8000/s2?limit=5"
   ```
6. **추천 목록 확인**  
   ```powershell
   Invoke-RestMethod -Uri "http://localhost:8000/recommendations"
   ```  
   쿼리 옵션: `?week_start=2026-03-03&topic_name=This%20Week&limit=10`
7. **추천 1건 삭제 (선택)**  
   ```powershell
   Invoke-RestMethod -Method Delete -Uri "http://localhost:8000/recommendations/<recommendation_id>"
   ```  
   `<recommendation_id>`는 GET /recommendations 응답의 `id` 값.

### 9.4 요약 체크리스트 (Recommendations 포함)

| Step | 작업 | 비고 |
|------|------|------|
| 0 | 51 + **52** 마이그레이션, .env, 테스트 유저 | S2_LOCAL_TEST.md와 동일 + 52 적용 |
| 1 | uvicorn 기동 | `--reload` 사용 시 .env 변경 후 재시작 |
| 2 | GET /me로 resolved_user_id 확인 | AUTH_BYPASS와 실제 처리 유저 일치 확인 |
| 3 | POST /jobs/s2 | 필요 시 week_start 지정 |
| 4 | POST /me/trigger-worker | S2 + 추천 생성 한 번에 처리 |
| 5 | GET /s2 | S2 성공 여부 |
| 6 | GET /recommendations | 추천 3건 들어왔는지, title/abstract/url 있는지 |
| 7 | DELETE /recommendations/{id} | 삭제 후 다시 GET으로 확인 |

### 9.5 S2 로컬 테스트 때 실수·고생했던 점 (그대로 주의)

- **마이그레이션 순서**: `51_jobs_payload` 먼저, 그 다음 `52_schema_recommendations`. 52는 `users` 테이블 존재 가정.
- **Auth bypass와 “지금 서버가 쓰는 유저”**  
  - S2/추천이 비어 있을 때, **요청한 유저**와 **서버가 인식한 유저**가 다를 수 있음.  
  - **GET /me**의 `resolved_user_id`가 실제로 S2/추천을 만들 유저(UUID)인지 먼저 확인.
- **.env 변경 후 서버 재시작**  
  - `AUTH_BYPASS_USER_ID`를 바꾼 뒤에는 **uvicorn을 반드시 재시작**해야 함. 재시작 안 하면 예전 유저로 동작.
- **S2 job은 enqueue 시점의 유저**  
  - POST /jobs/s2 호출 시점의 `get_user_id()`(즉 bypass면 AUTH_BYPASS_USER_ID)로 job이 저장됨.  
  - 유저를 바꾼 뒤에는 **새로** POST /jobs/s2 호출하고 trigger-worker를 돌려야 해당 유저로 S2·추천이 생성됨.
- **데이터 조건**  
  - S2가 되려면 “최근 7일 이내 소스 + 그 소스에 대한 S1 요약”이 있어야 함.  
  - 추천은 S2 job 성공 후 같은 주에 대해 생성되므로, S2가 한 건이라도 성공해야 해당 주에 대한 추천이 들어감.  
  - (s2_text를 DB에서 불러오는 경우) 해당 주의 S2가 이미 있어야 하므로, **먼저 S2가 성공한 상태**에서만 추천이 채워짐.
- **서버 로그로 확인**  
  - `s2 job created`, `trigger_worker: claimed job_id=...` 메시지.  
  - 추천 생성 실패 시 job은 성공으로 두고 payload에 `recommendations_failed`만 남기므로, 로그에 에러가 있어도 job 상태는 done.

### 9.6 Recommendations 전용 트러블슈팅

- **GET /recommendations가 빈 배열**  
  - 해당 유저로 S2 job이 한 번 성공했는지 확인 (GET /s2에 해당 주 요약이 있는지).  
  - job payload에 `recommendations_failed: true`가 있으면 arXiv/임베딩 쪽 실패 → 로그와 .env(OPENAI_API_KEY 등) 확인.
- **52 마이그레이션 적용 안 됨**  
  - `recommendations` 테이블이 없으면 insert 시 오류. Supabase에서 테이블 목록 확인 후 52 실행.
- **Process 플로우 (로컬에서만 API로 확인)**  
  - 앱과 동일하게: 해당 추천의 `url`로 **POST /ingest** 호출 후 **DELETE /recommendations/{id}** 호출하면 됨.  
  - POST /recommendations/{id}/ingest는 현재 미구현이면, 앱에서 두 번 호출로 처리.
