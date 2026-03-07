# Worker/tick 자동 실행 — Cloud Scheduler 설정

## 현재 상태 요약

- **BE 코드는 정상 동작합니다.**
  - `POST /ingest` → DB에 소스·job 생성 (`state='queued'`).
  - `POST /worker/tick` → `claim_one_queued_job()`로 queued job 1건 claim → `process_job(job_id)` 실행.
  - `POST /me/trigger-worker` (앱의 "Process" 버튼) → 동일하게 claim + process_job.

- **자동으로 진행이 안 되는 이유**  
  **Cloud Scheduler job이 없어서** `POST /worker/tick`이 주기적으로 호출되지 않습니다.  
  따라서 job은 queued 상태로만 쌓이고, 앱에서 "Process"를 눌러야 `POST /me/trigger-worker`가 호출되며 그때 한 건씩 처리됩니다.

---

## 해결: Cloud Scheduler job 생성

`POST /worker/tick`을 **1~2분마다** 호출하는 Cloud Scheduler job을 만들면, Share/Ingest 후 별도 조작 없이 자동으로 처리됩니다.

### 사전 확인

1. **Cloud Run 서비스 URL**  
   예: `https://orchestrator-xxxxx-ue.a.run.app` (본인 배포 URL).
2. **WORKER_TICK_SECRET**  
   Cloud Run 서비스에 설정한 환경변수. 설정해 두었다면 Scheduler 호출 시 **같은 값**을 헤더에 넣어야 합니다.  
   (`.env` / Secret Manager에 설정한 값 사용.)

### GCP 콘솔에서 생성

1. [Cloud Scheduler](https://console.cloud.google.com/cloudscheduler?project=my-learning-agent-488300) 이동.
2. **Create job**.
3. **Region**: `us-east1` (Cloud Run 서비스와 동일 권장).
4. **Frequency**: cron `*/2 * * * *` (2분마다) 또는 `*/1 * * * *` (1분마다).
5. **Target type**: HTTP.
6. **URL**: `https://<YOUR-CLOUD-RUN-URL>/worker/tick`
7. **HTTP method**: POST.
8. **Auth header**:  
   - **WORKER_TICK_SECRET을 쓰는 경우**  
     Add header → Name: `X-Worker-Tick-Secret`, Value: (Cloud Run에 넣은 시크릿과 동일한 문자열).  
   - 시크릿을 안 쓰면 헤더 생략 가능 (보안상 비권장).

저장 후 1~2분 지나면 job이 주기적으로 실행되고, queued 문서가 자동으로 처리됩니다.

### gcloud로 생성 (시크릿 사용 시)

```bash
# 변수 설정 (본인 값으로 교체)
export PROJECT_ID=$Example
export REGION=us-east1
export SERVICE_URL=https://YOUR-CLOUD-RUN-SERVICE-URL
export WORKER_TICK_SECRET=your-secret-value

gcloud scheduler jobs create http worker-tick \
  --project=$PROJECT_ID \
  --location=$REGION \
  --schedule="*/2 * * * *" \
  --uri="$SERVICE_URL/worker/tick" \
  --http-method=POST \
  --headers="X-Worker-Tick-Secret=$WORKER_TICK_SECRET"
```

(시크릿 미사용 시 `--headers` 줄을 제거.)

### 동작 확인

- Scheduler job 실행 후 Cloud Run 로그에서 `worker_tick: claimed job_id=...` 로그 확인.
- 또는 앱에서 Share로 URL 넣고 2분 정도 기다린 뒤 문서 목록/상세에서 요약 등이 채워지는지 확인.

---

## BE 흐름 참고

| 단계 | 주체 | 동작 |
|------|------|------|
| 1 | 앱 (Share/Ingest) | `POST /ingest` → DB에 source + job(queued) 생성 |
| 2 | **Cloud Scheduler** | 주기적으로 `POST /worker/tick` 호출 (이 job이 없으면 자동 처리 안 됨) |
| 3 | BE `/worker/tick` | `claim_one_queued_job()` → `process_job(job_id)` → PDF/URL 처리, 요약 등 |
| 대안 | 앱 "Process" | `POST /me/trigger-worker` (Bearer) → 위와 동일한 claim + process_job |

`CLOUD_RUN_MIGRATION_PLAN.md` §10.7, §10.8과 `ANDROID_CLOUD_E2E.md` §4.3도 함께 참고하면 됩니다.

---

## S2 주간 요약 스케줄 (금요일 00:00 미국 동부)

S2 consolidation은 **매주 금요일 00:00 미국 동부(ET)** 에 전체 사용자 대상으로 한 번씩 돌리도록 Cloud Scheduler를 추가할 수 있습니다.

### 동작

- **엔드포인트**: `POST /worker/s2-schedule`
- **인증**: `POST /worker/tick`과 동일하게 `X-Worker-Tick-Secret` 헤더 사용 (WORKER_TICK_SECRET 설정 시).
- **로직**: 최근 7일 이내에 소스가 하나라도 있는 사용자마다 S2 job 1건을 enqueue. `week_start`는 해당 주 월요일(YYYY-MM-DD).
- **실제 처리**: enqueue된 job은 기존 `POST /worker/tick`이 claim해서 처리 (job_type='s2' 분기).

### Cloud Scheduler 설정 (금요일 00:00 ET)

- **Frequency**: cron `0 0 * * 5` (매주 금요일 00:00).
- **Time zone**: `America/New_York` (미국 동부).
- **URL**: `https://<YOUR-CLOUD-RUN-URL>/worker/s2-schedule`
- **HTTP method**: POST.
- **Header**: `X-Worker-Tick-Secret`: (WORKER_TICK_SECRET과 동일).

gcloud 예시 (Bash):

```bash
export PROJECT_ID=your-project
export REGION=us-east1
export SERVICE_URL=https://YOUR-CLOUD-RUN-URL
export WORKER_TICK_SECRET=your-secret

gcloud scheduler jobs create http worker-s2-schedule \
  --project=$PROJECT_ID \
  --location=$REGION \
  --schedule="0 0 * * 5" \
  --time-zone="America/New_York" \
  --uri="$SERVICE_URL/worker/s2-schedule" \
  --http-method=POST \
  --headers="X-Worker-Tick-Secret=$WORKER_TICK_SECRET"
```

PowerShell (Windows):

```powershell
$env:PROJECT_ID = "your-project"
$env:REGION = "us-east1"
$env:SERVICE_URL = "https://YOUR-CLOUD-RUN-URL"
$env:WORKER_TICK_SECRET = "your-secret"

gcloud scheduler jobs create http worker-s2-schedule `
  --project=$env:PROJECT_ID `
  --location=$env:REGION `
  --schedule="0 0 * * 5" `
  --time-zone="America/New_York" `
  --uri="$env:SERVICE_URL/worker/s2-schedule" `
  --http-method=POST `
  --headers="X-Worker-Tick-Secret=$env:WORKER_TICK_SECRET"
```

### 로컬/테스트

- **스케줄러 없이**: 로컬에서는 Cloud Scheduler를 쓰지 않고, **기존 문서(최근 7일) 기준**으로 테스트하면 됩니다.
- **방법 1**: 앱/클라이언트에서 `POST /jobs/s2` (Bearer 인증) 호출 → 해당 사용자에 대해 S2 job 1건 enqueue. 그 다음 `POST /worker/tick` 또는 `POST /me/trigger-worker`로 job 처리.
- **방법 2**: 스크립트/쉘에서 `run_s2_consolidation(user_id, week_start=None, days=7)` 직접 호출 (DB에 이미 있는 소스/S1 기준).
- **GET /s2**: 생성된 S2 요약 목록 조회 (query: `week_start`, `limit`).
