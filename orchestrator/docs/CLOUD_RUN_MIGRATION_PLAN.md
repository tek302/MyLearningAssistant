# Cloud Run 이전 계획 (Tick-Driven)

**기준 문서:** `Cloud_BE_Requirements_v1.0.md`  
**현재:** 로컬 E2E 완료 (Firebase 실토큰, ingest, RAG document_id).  
**목표:** Cloud Run으로 API + Worker 배포, Scale-to-zero, 비용 단일 digit $/월.

---

## 1. 요구사항 요약 (v1.0)

| 항목 | 내용 |
|------|------|
| **인증** | Firebase ID Token, get_user_id(), resolve_user_id(firebase_uid). DB는 users.id 매핑. |
| **Ingest** | **Tick-Driven** 채택. POST /ingest → DB에 job(queued). Cloud Scheduler(1–2분) → POST /worker/tick → 1개 job claim → 처리 → done/failed. |
| **리전** | us-east1 (Supabase East US와 가깝게). |
| **리소스** | request 기반 과금, 0.25 vCPU, 512Mi, concurrency 1, min-instances 0. |
| **시크릿** | Firebase Admin JSON(파일 마운트), OpenAI API Key, Supabase. |

---

## 2. 현재 구조 vs 목표

### 지금 (로컬 / Week6)

```
POST /ingest  →  DB에 job insert  →  enqueue(job_id)  →  in-memory asyncio.Queue
                                                              ↓
lifespan  →  run_forever()  →  dequeue() (blocking)  →  process_job(job_id)
```

- **문제:** job이 **DB + 메모리 큐** 두 곳에 있음. Cloud Run은 요청 단위 생명주기라 프로세스가 죽으면 큐가 사라짐. Scale-to-zero 시 항상 실행 중인 `run_forever`가 없음.
- **해결:** job은 **DB만** 사용. 큐 제거. **외부에서 주기적으로** `/worker/tick` 호출 → DB에서 1개 claim → 처리.

### 목표 (Tick-Driven)

```
POST /ingest  →  DB에 job(state=queued) insert 만. enqueue 제거.
Cloud Scheduler (1–2 min)  →  POST /worker/tick
                                    ↓
/worker/tick  →  claim_one_job() (DB, FOR UPDATE SKIP LOCKED)  →  process_job(job_id)  →  200
```

- Job 소비는 **오직** `/worker/tick` 호출 시에만 발생.
- `run_forever` 제거, lifespan에서는 pool + Firebase만 초기화.

---

## 3. 구현 단계 (Phase 2 → Phase 3)

### Phase 2 — Tick-Driven Worker 구현 (코드 변경)

| # | 작업 | 설명 |
|---|------|------|
| 2.1 | **DB claim_one_job()** | `jobs` 테이블에서 `state='queued'` 1건을 `FOR UPDATE SKIP LOCKED`로 선택 후 `state='running'`으로 업데이트하고 job_id 반환. 없으면 None. |
| 2.2 | **POST /worker/tick** | (a) 인증: Cloud Scheduler만 호출하도록 헤더 시크릿 검사 (예: `X-CloudScheduler-Secret` 또는 OIDC). (b) `claim_one_job()` 호출 → 있으면 `process_job(job_id)` (기존 로직 재사용) → 200. 없으면 200 (no-op). |
| 2.3 | **POST /ingest** | `create_job` 후 **enqueue(job_id) 제거**. DB에만 남김. |
| 2.4 | **lifespan** | `run_forever` 태스크 제거. `init_pool`, `init_firebase`만 유지. |
| 2.5 | **job_queue.py** | 사용처 제거 후 삭제하거나, 로컬 개발용으로만 유지(환경변수로 분기). 권장: 제거하고 항상 DB 기반. |

**로컬 테스트:**  
- 앱 기동 후 POST /ingest로 job 생성 → DB에 queued 1건 확인.  
- 수동으로 POST /worker/tick 호출 (시크릿 헤더 포함) → 해당 job running → done/failed 확인.

### Phase 3 — Cloud Run 배포

| # | 작업 | 설명 |
|---|------|------|
| 3.1 | **Dockerfile** | Python 3.11+ 베이스, `orchestrator` 루트 기준. `pip install -r requirements.txt`, `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]`. |
| 3.2 | **서비스 구성** | **옵션 A (권장): 서비스 2개** — API 전용 + Worker 전용. Worker는 `/worker/tick`만 노출하는 경량 앱 또는 동일 앱의 다른 URL. **옵션 B:** 서비스 1개 — 동일 URL에 `/worker/tick` 포함, Scheduler가 같은 Cloud Run URL에 POST. |
| 3.3 | **API 서비스** | min-instances=0, 0.25 vCPU, 512Mi, concurrency 1. 환경변수: OPENAI_API_KEY, DATABASE_URL(또는 SUPABASE_DB_URL), GOOGLE_APPLICATION_CREDENTIALS=/secrets/firebase.json. Secret Manager에서 마운트. |
| 3.4 | **Worker 서비스** (옵션 A) | 동일 이미지, 진입점만 `/worker/tick` 호출용으로 제한하거나, 동일 FastAPI 앱에 `/worker/tick` 두고 Scheduler가 Worker 서비스 URL만 호출. min-instances=0, 동일 리소스. |
| 3.5 | **Cloud Scheduler** | us-east1. 주기: `*/2 * * * *` (2분) 또는 `*/1 * * * *` (1분). HTTP Target: Worker 서비스 URL + `/worker/tick`. Body 없음. 인증: OIDC(권장) 또는 헤더 시크릿. |
| 3.6 | **시크릿** | Firebase Admin JSON → Secret Manager → Cloud Run에 볼륨 마운트. OpenAI, Supabase는 환경변수로 주입. |
| 3.7 | **Android** | `BuildConfig.API_BASE_URL`을 Cloud Run API 서비스 URL로 변경. |

---

## 4. 서비스 분리 (옵션 A) 상세

- **이미지:** 하나. `app.main:app` (기존 FastAPI 앱에 `/worker/tick` 포함).
- **API 서비스:** `--port 8080`. 라우트: /health, /me, /ingest, /rag/answer, /documents 등. `/worker/tick`은 **호출 거부**하거나 무시하도록 설정 가능(선택). 또는 그냥 두어도 됨(URL을 알면 호출 가능하므로 인증 필수).
- **Worker 서비스:** 동일 이미지, 동일 앱. Cloud Run에서 **Worker 서비스 URL만** Scheduler에 등록. 즉, 같은 코드베이스로 서비스 2개 배포(URL만 다름). API 서비스 URL은 Android용, Worker 서비스 URL은 Scheduler용.
- **장점:** API 트래픽과 Scheduler 호출이 같은 인스턴스에 섞이지 않음. Worker는 tick 때만 깨어남.

**단일 서비스(옵션 B):**  
- 서비스 1개. Scheduler가 `https://xxx.run.app/worker/tick` 호출.  
- `/worker/tick`은 반드시 시크릿 또는 IAM으로 보호.  
- 구현이 단순하고, 비용도 거의 동일(둘 다 scale-to-zero).

---

## 5. claim_one_job() 스케치

PostgreSQL에서 한 건만 락 잡고 `running`으로 바꾸는 패턴 예시:

```python
# repo.py
def claim_one_queued_job(self) -> Optional[str]:
    """Claim one job with state='queued'; set state='running'. Returns job_id or None."""
    with self._get_connection() as conn:
        with conn.cursor() as cur:
            # Select one queued job and lock it
            cur.execute(
                """
                SELECT id FROM jobs
                WHERE state = 'queued'
                ORDER BY created_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """
            )
            row = cur.fetchone()
            if not row:
                return None
            job_id = str(row[0])
            cur.execute(
                "UPDATE jobs SET state = 'running', updated_at = now() WHERE id = %s",
                (job_id,),
            )
            conn.commit()
            return job_id
```

---

## 6. /worker/tick 보안

- **Cloud Scheduler OIDC:** Scheduler에 “Service account” 지정 → Cloud Run에서 “Invoker” 권한만 부여. Scheduler가 Bearer 토큰으로 호출하면 Cloud Run이 자동 검증. 앱에서는 추가 검사 불필요.
- **또는 헤더 시크릿:** 환경변수 `WORKER_TICK_SECRET` 설정. `/worker/tick` 핸들러에서 `X-Worker-Tick-Secret` (또는 v1.0에 적힌 대로) 일치 여부 확인. 불일치 시 403.

---

## 7. 로컬 테스트 (Windows PowerShell, Android 앱 없이)

**Android 로그인 불필요.** `.env`에서 인증 bypass를 켜면 `localhost`에서 uvicorn만 띄우고 curl/Invoke-RestMethod로 전체 플로우를 검증할 수 있다.

### 7.1 사전 준비

1. **`.env` 설정**  
   `orchestrator/.env`에 다음이 있어야 한다.
   - `APP_ENV=local` 또는 `DEBUG=true`
   - `AUTH_BYPASS_USER_ID=dev-user` (아무 문자열 가능, 이 값이 “로그인한 사용자”로 쓰임)
   - (선택) `WORKER_TICK_SECRET=my-secret` — 설정하면 `/worker/tick` 호출 시 아래처럼 헤더 필요.

2. **DB·Firebase**  
   Supabase(DB), 필요하면 Firebase 설정은 그대로 두고, bypass 시 Firebase 토큰은 사용하지 않는다.

### 7.2 서버 실행

PowerShell에서:

```powershell
cd C:\Users\taekh\AndroidStudioProjects\TekLearningAgent\orchestrator
# 가상환경 활성화 (사용 중인 경우)
# .\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

브라우저에서 `http://localhost:8000/docs` 로 접속해 API 문서 확인.

### 7.3 Step 1: POST /ingest (job 큐에 넣기)

Bypass 사용 시 `Authorization: Bearer dev-user` 로 호출한다. (`AUTH_BYPASS_USER_ID`와 동일한 값)

**URL 타입 예 (간단한 웹 페이지):**

```powershell
$body = @{
  type = "url"
  content = "https://example.com"
  title = "Example"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/ingest" -Method Post `
  -ContentType "application/json" `
  -Headers @{ "Authorization" = "Bearer dev-user" } `
  -Body $body
```

응답 예: `job_id`, `status: "queued"`. 이 `job_id`를 복사해 둔다.

**PDF URL 타입 예:**  
(실제 PDF URL을 쓰거나, Windows에서 SSL 오류가 나면 아래 7.3.1 참고.)

```powershell
$body = @{
  type = "pdf_url"
  content = "https://arxiv.org/pdf/2512.02556.pdf"
  title = "DeepSeek_V3.2"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/ingest" -Method Post `
  -ContentType "application/json" `
  -Headers @{ "Authorization" = "Bearer dev-user" } `
  -Body $body
```

**7.3.1 PDF 테스트 시 SSL 오류 (Windows)**  
`CERTIFICATE_VERIFY_FAILED` / `unable to get local issuer certificate` 가 나오면:

- **로컬 전용:** `.env`에 `SKIP_SSL_VERIFY=true` 추가. (`APP_ENV=local` 또는 `DEBUG=true` 일 때만 적용되며, 프로덕션에서는 무시됨.)
- 또는 **검증된 PDF URL**로 테스트: 예) 공개 PDF 링크(실제 문서 URL) 사용. `example.com/sample.pdf` 는 실제 PDF가 아닐 수 있음.

### 7.4 Step 2: POST /worker/tick (한 건 처리)

- **`WORKER_TICK_SECRET`을 설정한 경우**  
  헤더에 시크릿을 넣어야 한다.

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/worker/tick" -Method Post `
  -Headers @{ "X-Worker-Tick-Secret" = "my-secret" }
```

- **`WORKER_TICK_SECRET`을 비워 둔 경우**  
  헤더 없이 호출한다.

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/worker/tick" -Method Post
```

응답 예: `{ "status": "ok", "processed": true, "job_id": "..." }`  
큐에 job이 없으면 `processed: false` 이고 `job_id` 없음.

### 7.5 Step 3: GET /ingest/status (job 상태 확인)

Step 1에서 받은 `job_id`로 상태 조회. 역시 bypass 사용 시 `Authorization: Bearer dev-user`.

```powershell
$jobId = "여기에-Step1에서-받은-job_id-넣기"
Invoke-RestMethod -Uri "http://localhost:8000/ingest/status?job_id=$jobId" -Method Get `
  -Headers @{ "Authorization" = "Bearer dev-user" }
```

응답 예: `state`가 `queued` → `running` → `done` 또는 `failed`, `progress`, `error`(실패 시) 등.

### 7.6 curl로 할 때 (PowerShell에 curl 있을 때)

```powershell
# POST /ingest
curl -X POST "http://localhost:8000/ingest" `
  -H "Authorization: Bearer dev-user" `
  -H "Content-Type: application/json" `
  -d '{\"type\":\"url\",\"content\":\"https://example.com\",\"title\":\"Example\"}'

# POST /worker/tick (시크릿 설정한 경우)
curl -X POST "http://localhost:8000/worker/tick" -H "X-Worker-Tick-Secret: my-secret"

# GET /ingest/status
curl "http://localhost:8000/ingest/status?job_id=YOUR_JOB_ID" -H "Authorization: Bearer dev-user"
```

### 7.7 정리

| 항목 | 설명 |
|------|------|
| Android 앱 | 필요 없음. 브라우저 로그인/앱 로그인 불필요. |
| 인증 | `APP_ENV=local`(또는 `DEBUG=true`) + `AUTH_BYPASS_USER_ID=dev-user` 이면 `Authorization: Bearer dev-user` 로 모든 인증 API 호출 가능. |
| /worker/tick | `WORKER_TICK_SECRET` 없으면 헤더 없이 호출; 있으면 `X-Worker-Tick-Secret` 필수. |

---

## 8. 체크리스트 (배포 전)

- [x] Phase 2 코드 반영: claim_one_job, /worker/tick, enqueue 제거, run_forever 제거.
- [x] 로컬에서 /ingest → DB queued → /worker/tick 한 번 호출로 job 처리 확인.
- [ ] Dockerfile 빌드 및 로컬에서 `docker run -p 8080:8080` 동작 확인.
- [ ] Cloud Run API 서비스 배포, /health, /me (토큰) 확인.
- [ ] Cloud Run Worker 서비스 배포(동일 이미지), /worker/tick 수동 호출로 job 소비 확인.
- [ ] Cloud Scheduler job 생성, 1–2분 후 DB에서 job 완료 여부 확인.
- [ ] Android API_BASE_URL 변경 후 앱에서 ingest → 문서 목록·RAG E2E 확인.

이 문서는 `Cloud_BE_Requirements_v1.0.md`와 `ROADMAP_USAGE_AND_CLOUD.md` Session 2를 함께 보면서 Cloud Run 이전 시 참고용으로 쓸 수 있음.
