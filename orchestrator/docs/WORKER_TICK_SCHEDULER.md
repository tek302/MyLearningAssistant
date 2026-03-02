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
export PROJECT_ID=my-learning-agent-488300
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
