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
| 3.1 | **Dockerfile** | Python 3.12-slim 베이스, `orchestrator` 디렉터리 기준. `pip install -r requirements.txt`, `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]`. |
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
- [x] **3.1 Docker 로컬 확인:** 아래 §9 명령으로 빌드 후 `http://localhost:8080/health` 및 `/worker/tick` 확인.
- [ ] Cloud Run API 서비스 배포, /health, /me (토큰) 확인.
- [ ] Cloud Run Worker 서비스 배포(동일 이미지), /worker/tick 수동 호출로 job 소비 확인.
- [ ] Cloud Scheduler job 생성, 1–2분 후 DB에서 job 완료 여부 확인.
- [ ] Android API_BASE_URL 변경 후 앱에서 ingest → 문서 목록·RAG E2E 확인.

---

## 9. Phase 3.1 — Docker 로컬 빌드/실행 (한 단계씩)

**전제:** Docker Desktop 등 Docker가 설치되어 있고, `orchestrator/.env`가 있음 (로컬 테스트용).

**1) 이미지 빌드** (orchestrator 디렉터리에서):

```powershell
cd C:\Users\taekh\AndroidStudioProjects\TekLearningAgent\orchestrator
docker build -t orchestrator .
```

**2) 컨테이너 실행** (포트 8080, .env 주입):

```powershell
docker run -p 8080:8080 --env-file .env orchestrator
```

**3) 확인:**

- 브라우저 또는 PowerShell: `Invoke-RestMethod -Uri "http://localhost:8080/health"` → `{"status":"healthy"}`
- `Invoke-RestMethod -Uri "http://localhost:8080/worker/tick" -Method Post` → `{ "status": "ok", "processed": ... }`

**4) 중지:** 컨테이너 실행 중인 터미널에서 `Ctrl+C`.

**5) DB 연결 오류 (IPv6 unreachable):**  
`Network is unreachable` / `1f16:1cd0:... port 5432` 처럼 **IPv6 주소**로 연결하려다 실패하면, Docker 안에서는 DNS가 IPv4를 안 줄 수 있음. 이때 **IPv4 전용 URL**을 쓰면 됨.

- Windows에서 Supabase DB 호스트의 IPv4 확인:
  ```powershell
  nslookup db.프로젝트ref.supabase.co
  ```
  또는 풀러 쓰면: `nslookup aws-0-us-east-1.pooler.supabase.com` (호스트는 `.env`의 `SUPABASE_DB_URL`에 있는 주소).
- **A 레코드(Address)** 에 나온 IP 하나를 복사한 뒤, 기존 URL에서 호스트만 그 IP로 바꾼 문자열을 만듦.  
  예: `postgresql://postgres.xxx:[password]@기존호스트:5432/postgres` → `postgresql://postgres.xxx:[password]@13.xx.xx.xx:5432/postgres`
- `.env`에 **한 줄 추가** (기존 `SUPABASE_DB_URL`은 그대로 두고):
  ```
  DATABASE_URL_IPV4=postgresql://postgres.xxx:[password]@13.xx.xx.xx:5432/postgres
  ```
- 그 다음: `docker run -p 8080:8080 --env-file .env orchestrator` 다시 실행.  
  앱은 `DATABASE_URL_IPV4`가 있으면 이 URL만 사용하고, 호스트 이름 해석을 하지 않음.

이 단계까지 성공하면 체크리스트의 "Dockerfile 빌드 및 로컬 docker run 동작 확인"을 완료한 뒤, 3.2~3.7(Cloud Run 배포·Scheduler·Android) 순서로 진행하면 됨.

---

## 10. Phase 3.2~3.6 — Cloud Run 배포 (한 단계씩)

**옵션 B(단일 서비스)** 기준: 서비스 1개에 API + `/worker/tick` 모두 두고, Scheduler가 같은 URL의 `/worker/tick`을 호출.

### 10.1 사전 준비

- **GCP 프로젝트** 생성 및 과금(결제) 계정 연결.
- **gcloud CLI** 설치: https://cloud.google.com/sdk/docs/install  
  설치 후 `gcloud init` 로 로그인·프로젝트 선택.
- 아래에서 `PROJECT_ID`, `REGION`(예: us-east1)은 본인 값으로 바꿀 것.

```powershell
# 프로젝트/리전 변수 (본인 값으로 수정)
$PROJECT_ID = "your-gcp-project-id"
$REGION = "us-east1"
gcloud config set project $PROJECT_ID
```

### 10.2 API 활성화

```powershell
gcloud services enable run.googleapis.com
gcloud services enable artifactregistry.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable cloudscheduler.googleapis.com
```

### 10.3 이미지 빌드 및 푸시 (Cloud Build)

Windows에서 로컬 Docker로 푸시하지 않고, **Cloud Build**로 소스만 보내서 GCP에서 빌드·푸시.

```powershell
cd C:\Users\taekh\AndroidStudioProjects\TekLearningAgent

# Artifact Registry 저장소 생성 (최초 1회)
gcloud artifacts repositories create orchestrator --repository-format=docker --location=$REGION

# orchestrator 폴더를 컨텍스트로 빌드 (해당 폴더 안의 Dockerfile 사용)
gcloud builds submit --tag $REGION-docker.pkg.dev/$PROJECT_ID/orchestrator/orchestrator orchestrator
```

빌드가 끝나면 이미지가 `$REGION-docker.pkg.dev/$PROJECT_ID/orchestrator/orchestrator` 에 올라감.

### 10.4 시크릿 생성 (Secret Manager)

**모든 비밀(API 키·DB URL·Worker 시크릿)은 반드시 Secret Manager에 등록하고, Cloud Run에서는 시크릿만 참조한다.**

#### 1) Firebase Admin JSON (파일 시크릿)

```powershell
gcloud secrets create firebase-admin-json --data-file=orchestrator/firebase_myla_admin.json
```

이미 있으면: `gcloud secrets versions add firebase-admin-json --data-file=orchestrator/firebase_myla_admin.json`

#### 2) WORKER_TICK_SECRET (헤더 시크릿 — Scheduler가 `/worker/tick` 호출 시 사용)

PowerShell에서 값만 파일로 넘기기 (구버전 PowerShell도 동작):

```powershell
# 원하는 시크릿 문자열로 교체 (예: 랜덤 문자열)
$secretValue = "your-strong-random-secret-here"
# 새 줄 없이 파일로 저장 (PowerShell 5.x 호환)
[System.IO.File]::WriteAllText("$PWD\worker_tick_secret.txt", $secretValue)
gcloud secrets create worker-tick-secret --data-file=worker_tick_secret.txt
Remove-Item worker_tick_secret.txt
```

이미 있으면: `[System.IO.File]::WriteAllText(...)` 후 `gcloud secrets versions add worker-tick-secret --data-file=worker_tick_secret.txt`

#### 3) OPENAI_API_KEY, SUPABASE_DB_URL (반드시 Secret Manager 사용)

- **OPENAI_API_KEY:** OpenAI API 키 문자열.
- **SUPABASE_DB_URL:** 반드시 **Pooler 연결 문자열**만 사용 (Direct `db.xxx.supabase.co` 아님).  
  형식 예: `postgresql://postgres.[project-ref]:[password]@aws-0-us-east-1.pooler.supabase.com:5432/postgres` 또는 `aws-1-us-east-2.pooler.supabase.com` 등.

GCP 콘솔에서 생성 권장: **Secret Manager** → **Create Secret** → 이름 `openai-api-key` / `supabase-db-url`, 값에 위 값 입력.

또는 PowerShell로 (값은 본인 것으로 교체). 새 줄 없이 저장하려면 `[System.IO.File]::WriteAllText` 사용.

```powershell
# OPENAI_API_KEY
[System.IO.File]::WriteAllText("$PWD\oai.txt", "sk-proj-xxxx")
gcloud secrets create openai-api-key --data-file=oai.txt
Remove-Item oai.txt

# SUPABASE_DB_URL — 반드시 pooler 호스트 (aws-x-region.pooler.supabase.com)
[System.IO.File]::WriteAllText("$PWD\dburl.txt", "postgresql://postgres.xxx:PASSWORD@aws-1-us-east-2.pooler.supabase.com:5432/postgres")
gcloud secrets create supabase-db-url --data-file=dburl.txt
Remove-Item dburl.txt
```

**SUPABASE_URL** 은 DB 연결이 아니라 프로젝트 API 주소(`https://[project-ref].supabase.co`)이므로 시크릿이 아니다. 10.5에서 일반 환경변수로만 넣으면 된다.

### 10.5 Cloud Run 서비스 배포

**비밀은 모두 Secret Manager에서만 가져온다.** 환경변수로 넣는 것은 비밀번호가 아닌 것만(예: `APP_ENV`, `SUPABASE_URL`).

- **SUPABASE_URL:** `https://[project-ref].supabase.co` (REST API 주소). **Direct DB 주소(`db.xxx.supabase.co`)가 아님.**
- **SUPABASE_DB_URL, OPENAI_API_KEY, WORKER_TICK_SECRET:** 반드시 시크릿 참조(`--set-secrets`).

```powershell
$IMAGE = "$REGION-docker.pkg.dev/$PROJECT_ID/orchestrator/orchestrator"

# Cloud_BE_Requirements_v1.0 §5: 1 vCPU, 512Mi, concurrency 1, min-instances 0 (Free Tier 내 저트래픽 시 무료)
gcloud run deploy orchestrator `
  --image $IMAGE `
  --region $REGION `
  --platform managed `
  --allow-unauthenticated `
  --port 8080 `
  --cpu 1 `
  --memory 512Mi `
  --concurrency 1 `
  --min-instances 0 `
  --max-instances 10 `
  --set-env-vars "APP_ENV=production,SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co,GOOGLE_APPLICATION_CREDENTIALS=/secrets/firebase.json" `
  --set-secrets "/secrets/firebase.json=firebase-admin-json:latest,WORKER_TICK_SECRET=worker-tick-secret:latest,OPENAI_API_KEY=openai-api-key:latest,SUPABASE_DB_URL=supabase-db-url:latest"
```

- **SUPABASE_URL:** `YOUR_PROJECT_REF` 를 본인 Supabase 프로젝트 ref로 바꿀 것. (예: `voyoolgvujipuodxxfwl` → `https://voyoolgvujipuodxxfwl.supabase.co`). DB 연결용이 아니라 REST/Auth용 URL이다.
- **SUPABASE_DB_URL** 시크릿에는 10.4에서 넣은 **Pooler URL**(`aws-x-region.pooler.supabase.com`)만 들어가 있어야 한다. Direct(`db.xxx.supabase.co`) 사용 금지.
- **CPU/메모리/동시성:** `Cloud_BE_Requirements_v1.0.md` §5 기준 — 1 vCPU, 512Mi, concurrency 1, min-instances 0. 저트래픽(주 2~3회 ingest 등)이면 Free Tier(월 180,000 vCPU초, 200만 요청) 내로 가능.
- Firebase는 파일로 마운트(`/secrets/firebase.json`), 나머지 세 개는 환경변수로 주입된다.
- **시크릿 권한:** 배포 시 "Permission denied on secret" 나오면, Cloud Run 서비스 계정에 **Secret Manager Secret Accessor** 부여.  
  `gcloud projects add-iam-policy-binding PROJECT_ID --member="serviceAccount:PROJECT_NUMBER-compute@developer.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"`

### 10.6 배포 후 확인

배포가 끝나면 **서비스 URL**이 나옴 (예: `https://orchestrator-xxxxx-uc.a.run.app`).

```powershell
$SERVICE_URL = "https://orchestrator-xxxxx-uc.a.run.app"   # 실제 URL로 교체

# Health
Invoke-RestMethod -Uri "$SERVICE_URL/health"

# /worker/tick — WORKER_TICK_SECRET 사용 시 반드시 헤더 포함
Invoke-RestMethod -Uri "$SERVICE_URL/worker/tick" -Method Post -Headers @{ "X-Worker-Tick-Secret" = "여기에-10.4에서-설정한-시크릿-값" }
```

`/me` 는 Firebase 토큰이 필요하므로, Android 앱이나 Postman으로 Bearer 토큰 넣어서 호출.

### 10.7 Cloud Scheduler (주기적으로 /worker/tick 호출) — WORKER_TICK_SECRET 사용

Scheduler가 1~2분마다 `POST /worker/tick` 호출 시, **헤더 `X-Worker-Tick-Secret`** 에 10.4에서 만든 시크릿과 **동일한 값**을 넣는다.

- **콘솔:** Cloud Scheduler → Create Job → Target type: HTTP → URL: `https://your-service.run.app/worker/tick`, Method: POST  
  → **Headers** (또는 "Add header"): 이름 `X-Worker-Tick-Secret`, 값에 `worker-tick-secret` 시크릿과 같은 문자열 입력.
- **gcloud 예시 (값을 직접 넣는 경우):**
  ```powershell
  gcloud scheduler jobs create http worker-tick --location=$REGION --schedule="*/2 * * * *" --uri="$SERVICE_URL/worker/tick" --http-method=POST --headers="X-Worker-Tick-Secret=동일한시크릿값"
  ```
  시크릿 값을 gcloud에 직접 쓰지 않으려면 콘솔에서 Job을 만들고 Headers에만 입력하면 된다.

### 10.8 체크리스트 갱신

- [x] 10.2 API 활성화
- [x] 10.3 이미지 빌드·푸시
- [x] 10.4 Firebase·WORKER_TICK_SECRET·OPENAI_API_KEY·SUPABASE_DB_URL 시크릿 생성
- [x] 10.5 Cloud Run 배포 (서비스 계정 Secret Accessor 부여 후 deploy)
- [x] 10.6 /health, /worker/tick 확인
- [ ] 10.7 Cloud Scheduler job 생성
- [ ] Android `API_BASE_URL` → Cloud Run URL 변경 후 E2E

Android ↔ Cloud 연동 및 E2E 셋업·테스트는 **`ANDROID_CLOUD_E2E.md`** 참고.

---

이 문서는 `Cloud_BE_Requirements_v1.0.md`와 `ROADMAP_USAGE_AND_CLOUD.md` Session 2를 함께 보면서 Cloud Run 이전 시 참고용으로 쓸 수 있음.
