# S2 consolidation 로컬 테스트 (Step-by-Step)

Android 앱 로그인 없이 로컬에서 S2 주간 요약을 테스트하는 방법입니다.  
**uvicorn으로 서버를 띄운 뒤** Auth bypass로 API를 호출하는 방식이 기본입니다.  
(Windows PowerShell 기준으로 작성됨)

---

## 사전 준비

### Step 0-1. DB 마이그레이션

S2 job에 `payload` 컬럼이 필요합니다.

- **Supabase SQL Editor**: 대시보드에서 `sql/51_jobs_payload.sql` 내용 복사 후 실행  
- **psql** (로컬에 설치된 경우):

```powershell
cd orchestrator
psql $env:SUPABASE_DB_URL -f sql/51_jobs_payload.sql
```

### Step 0-2. .env 설정

`.env`에 다음을 설정합니다.

| 변수 | 설명 |
|------|------|
| `SUPABASE_DB_URL` | DB 연결 문자열 (또는 `DATABASE_URL`) |
| `OPENAI_API_KEY` | S2 요약 생성에 사용 |
| `APP_ENV` | `local` 로 설정 |
| `AUTH_BYPASS_USER_ID` | 테스트할 유저 ID (UUID 또는 firebase_uid) |

Firebase 자격 증명(`GOOGLE_APPLICATION_CREDENTIALS` 등)은 **설정하지 않으면** bypass 모드로 기동됩니다.

### Step 0-3. 테스트용 유저 확인

S2는 **최근 7일 이내 소스**와 그 소스에 대한 **S1 요약**이 있어야 합니다. Supabase SQL Editor에서 실행:

```sql
SELECT s.user_id, count(*) AS sources, count(ss.id) AS s1_count
FROM sources s
LEFT JOIN summaries ss ON ss.source_id = s.id AND ss.scope = 'doc' AND ss.kind = 'S1'
WHERE s.created_at >= now() - interval '7 days'
GROUP BY s.user_id
HAVING count(ss.id) > 0
LIMIT 1;
```

결과의 `user_id`(UUID)를 `.env`의 `AUTH_BYPASS_USER_ID`에 넣습니다.

---

## 방법 A: uvicorn 서버 + API 호출 (권장)

로컬에 uvicorn 서버를 띄우고, Bearer 토큰 없이 API로 S2를 enqueue → 처리 → 조회합니다.

### Step 1. uvicorn 서버 기동

새 PowerShell 창에서:

```powershell
cd orchestrator
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Firebase 자격 증명이 없으면 auth bypass 모드로 기동됩니다.  
`Uvicorn running on http://0.0.0.0:8000` 메시지가 보이면 정상입니다.

### Step 2. S2 job 넣기

다른 PowerShell 창에서 (서버는 그대로 실행 중):

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/jobs/s2" -ContentType "application/json" -Body "{}"
```

`week_start`를 지정할 때:

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/jobs/s2" -ContentType "application/json" -Body '{"week_start": "2025-12-30"}'
```

응답 예: `job_id`, `status` 필드가 보이면 성공입니다.

### Step 3. 한 건 처리 (worker tick)

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/me/trigger-worker"
```

응답 예: `status: ok`, `processed: True`, `job_id: ...`  
`processed: False`이면 Step 2를 다시 하거나, 한 번 더 호출해 보세요 (다른 job이 먼저 처리되었을 수 있음).

### Step 4. S2 결과 확인

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/s2?limit=5"
```

`week_start`로 필터:

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/s2?week_start=2026-02-20&limit=5"
```

`summaries` 배열에 S2 요약이 있으면 성공입니다.

---

## 방법 B: Python 스크립트 (서버 없이)

uvicorn을 띄우지 않고, DB + S2 로직만 실행해서 확인하는 방법입니다.

### Step 1. 스크립트 실행

```powershell
cd orchestrator
python scripts/run_s2_local.py
```

최근 7일 이내 소스가 있는 유저 한 명에 대해 S2 consolidation이 실행됩니다.

### Step 2. DB로 결과 확인

Supabase SQL Editor에서:

```sql
SELECT id, user_id, scope, kind, tldr, bullets, extra, created_at
FROM summaries
WHERE scope = 'topic' AND kind = 'S2'
ORDER BY created_at DESC
LIMIT 5;
```

---

## 요약 체크리스트 (방법 A)

| Step | 작업 | 명령 |
|------|------|------|
| 0 | 마이그레이션 + .env + 테스트 유저 준비 | 위 “사전 준비” 참고 |
| 1 | uvicorn 서버 기동 | `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` |
| 2 | S2 job 넣기 | `Invoke-RestMethod -Method Post -Uri "http://localhost:8000/jobs/s2" -ContentType "application/json" -Body "{}"` |
| 3 | Worker tick 호출 | `Invoke-RestMethod -Method Post -Uri "http://localhost:8000/me/trigger-worker"` |
| 4 | S2 조회 | `Invoke-RestMethod -Uri "http://localhost:8000/s2?limit=5"` |

---

## 트러블슈팅

- **마이그레이션**: `51_jobs_payload.sql` 적용 여부 확인  
- **데이터**: 최근 7일 이내 소스 + 해당 소스 S1 요약 존재 여부  
- **Auth bypass**: `.env`에 `APP_ENV=local`, `AUTH_BYPASS_USER_ID` 설정, Firebase 관련 변수는 비워 둠  
- **서버 로그**: `s2 job created`, `trigger_worker: claimed job_id=...` 메시지 확인  

### “지금 서버가 어떤 유저로 인식하는지” 확인 (AUTH_BYPASS vs 실제 S2)

S2가 비어 있을 때, **실제로 S2를 요청한 유저**와 **서버가 쓰는 유저**가 다를 수 있습니다. 아래 순서로 확인하세요.

1. **서버가 쓰는 유저 확인**  
   ```powershell
   Invoke-RestMethod -Uri "http://localhost:8000/me"
   ```  
   - `firebase_uid`: `.env`의 `AUTH_BYPASS_USER_ID` 값(문자열 그대로).  
   - `resolved_user_id`: DB의 `users.id`(UUID). **이 UUID가 모든 API(jobs, S2, documents)에 사용됩니다.**

2. **.env 변경 후에는 서버 재시작**  
   `AUTH_BYPASS_USER_ID`를 바꾼 뒤에는 **uvicorn을 반드시 재시작**해야 새 값이 적용됩니다. 재시작하지 않으면 예전 유저로 계속 동작합니다.

3. **유저를 바꾼 뒤에는 S2 job을 새로 넣기**  
   S2 job은 **enqueue 시점의 유저**로 저장됩니다.  
   - 예: 처음에 유저 A로 `POST /jobs/s2` → job의 `user_id` = A.  
   - 그 다음 `.env`를 유저 B로 바꾸고 서버 재시작.  
   - 이전에 넣은 job은 그대로 **A용**이라, trigger-worker가 처리해도 S2는 **A** 기준으로만 생성됩니다.  
   - **B**로 S2를 쓰려면, **B로 설정한 뒤** `POST /jobs/s2`를 다시 호출하고 trigger-worker를 돌려야 합니다.

4. **DB에서 “지난주 PDF 넣은 유저” 확인**  
   Supabase SQL에서 최근 소스가 많은 유저를 찾습니다.  
   ```sql
   SELECT u.id, u.firebase_uid,
          (SELECT count(*) FROM sources s WHERE s.user_id = u.id AND s.created_at >= now() - interval '7 days') AS sources_7d,
          (SELECT count(*) FROM summaries sm JOIN sources s ON sm.source_id = s.id AND s.user_id = u.id WHERE sm.scope = 'doc' AND sm.kind = 'S1') AS s1_count
   FROM users u
   ORDER BY sources_7d DESC
   LIMIT 5;
   ```  
   - S2를 만들려면 `sources_7d >= 1` 이고 `s1_count >= 1` 인 유저를 써야 합니다.  
   - 그 유저의 `id`(UUID) 또는 `firebase_uid`를 `.env`의 `AUTH_BYPASS_USER_ID`에 넣고, **서버 재시작** 후 `POST /jobs/s2` → trigger-worker → `GET /s2` 순서로 다시 시도하세요.

5. **정리**  
   - **S2가 안 나온다** → `GET /me`의 `resolved_user_id`와 DB의 그 유저 소스/S1을 위 SQL로 확인.  
   - **다른 유저로 바꿨다** → `.env` 수정 후 **서버 재시작** + **새로** `POST /jobs/s2` 후 trigger-worker.

---

프로덕션/Cloud Scheduler: `WORKER_TICK_SCHEDULER.md`의 “S2 주간 요약 스케줄” 섹션 참고.
