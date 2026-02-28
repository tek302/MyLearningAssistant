# Android ↔ Cloud Run 연동 및 E2E 테스트

**전제:** Cloud Run에 orchestrator 서비스가 배포되어 있고, 10.6까지 완료된 상태.  
**목표:** Android 앱이 Cloud Run API를 바라보도록 설정하고, ingest → 문서 목록 → RAG까지 E2E로 검증.

---

## 1. 사전 확인

- [ ] Cloud Run 서비스 URL 확인 (예: `https://orchestrator-xxxxx-ue.a.run.app`)
- [ ] `/health`, `/worker/tick`(헤더 포함) 로컬에서 호출해 응답 확인
- [ ] (선택) Cloud Scheduler job 생성 후 2분마다 `/worker/tick` 호출되는지 확인

---

## 2. Android 셋업 — API Base URL

앱이 **Cloud Run**을 백엔드로 쓰려면 API 베이스 URL을 로컬에서 원격으로 바꾼다.

### 2.1 URL이 들어가는 위치

- **BuildConfig / 빌드 변수:** `API_BASE_URL` 또는 `BASE_URL` 같은 항목을 Cloud Run 서비스 URL로 설정.
- 위치 예: `android/app/build.gradle.kts` 또는 `build.gradle`, `BuildConfig.API_BASE_URL`, 또는 `local.properties` / `gradle` 변수.

프로젝트에서 실제로 쓰는 방식을 확인한 뒤, 아래처럼 **배포된 URL만** 넣는다 (끝에 슬래시 없이).

```text
https://orchestrator-xxxxx-ue.a.run.app
```

### 2.2 예시 (BuildConfig)

`android/app/build.gradle.kts` 또는 `build.gradle` 에서:

```kotlin
buildTypes {
    release {
        buildConfigField("String", "API_BASE_URL", "\"https://orchestrator-xxxxx-ue.a.run.app\"")
    }
    debug {
        buildConfigField("String", "API_BASE_URL", "\"https://orchestrator-xxxxx-ue.a.run.app\"")
    }
}
```

또는 `local.properties`에 넣고 빌드에서 읽는 방식이면:

```properties
API_BASE_URL=https://orchestrator-xxxxx-ue.a.run.app
```

- **로컬 백엔드로 되돌리기:** 위 값을 `http://10.0.2.2:8000`(에뮬레이터) 또는 `http://본인PC_IP:8000`(실기기)으로 바꾸면 된다.

### 2.3 네트워크 보안 (Cleartext)

- Cloud Run은 **HTTPS**이므로 별도 Cleartext 설정 불필요.
- 나중에 로컬 `http://` 로 테스트할 때만 `android:usesCleartextTraffic="true"` 또는 network security config 필요할 수 있음.

---

## 3. 인증 (Firebase)

- 앱은 **Firebase ID Token**을 `Authorization: Bearer <token>` 으로 보낸다.
- Cloud Run 쪽은 **Firebase Admin**으로 토큰 검증 후 `get_user_id()` → DB `resolve_user_id` 로 매핑한다.
- **AUTH_BYPASS** 는 프로덕션/Cloud Run에서는 사용하지 말 것 (로컬 전용).

할 일:

- [ ] 앱에서 로그인 후 토큰이 비어 있지 않은지 확인
- [ ] Cloud Run 배포 시 Firebase Admin JSON(시크릿)이 올바르게 마운트되어 있는지 확인 (이미 10.5에서 설정했다면 생략)

---

## 4. E2E 테스트 순서

아래 순서로 한 번씩 실행해 보면 된다.

### 4.1 로그인 및 /me

1. 앱에서 **Google 로그인** 후 메인 화면까지 진입
2. (선택) 백엔드 `/me` 호출이 성공하는지 로그/네트워크로 확인  
   - 기대: `200`, body에 `firebase_uid` 등

### 4.2 Ingest (URL 또는 PDF)

1. 앱에서 **URL 추가** 또는 **PDF URL** ingest 실행
2. 응답에서 `job_id` 수신 확인
3. (선택) Supabase 대시보드에서 `jobs` 테이블에 해당 `job_id`로 `state='queued'` 또는 `state='running'` / `state='done'` 확인

### 4.3 Worker 처리 (Scheduler 또는 앱/수동)

- **Cloud Scheduler 사용 시:** 1~2분 이내에 자동으로 `POST /worker/tick` 이 호출되어 job이 처리됨. DB에서 `state='done'` 또는 `failed` 로 바뀌는지 확인.
- **앱에서 수동 처리:** 문서 카드에서 **Process** 버튼 클릭 → `POST /me/trigger-worker` 호출 (Bearer 인증). Scheduler 없이 즉시 처리 가능.
- **PowerShell 수동 호출:**  
  `Invoke-RestMethod -Uri "https://서비스URL/worker/tick" -Method Post -Headers @{ "X-Worker-Tick-Secret" = "시크릿값" }`  
  로 한 번 호출한 뒤, DB에서 해당 job이 처리되었는지 확인.

### 4.4 문서 목록

1. 앱에서 **문서 목록** 화면 열기
2. 방금 ingest한 소스가 **문서로 보이고**, 상태가 완료로 나오는지 확인
3. **새로고침:** 상단 새로고침 아이콘 또는 아래로 당기기(pull-to-refresh)로 목록 갱신
4. **상태 표시:** 각 카드에 Pending / Processing / Done / Failed 칩 표시
5. **Pending 카드:** Refresh(목록 갱신), Process(수동 worker tick) 버튼으로 즉시 처리 가능

### 4.5 RAG 질의

1. 앱에서 **RAG 질의**(해당 문서 기반 질문) 실행
2. 응답이 정상적으로 오는지, 필요하면 에러 로그 확인

---

## 5. 체크리스트 요약

| 단계 | 확인 항목 |
|------|-----------|
| 셋업 | Android `API_BASE_URL` = Cloud Run 서비스 URL |
| 셋업 | Firebase 로그인 후 토큰 전달 확인 |
| E2E | 로그인 → /me (또는 메인 진입) 성공 |
| E2E | Ingest(URL/PDF) → job_id 수신 |
| E2E | Worker 처리 후(스케줄러 또는 수동 tick) job 완료 |
| E2E | 문서 목록에 해당 문서 표시 |
| E2E | RAG 질의 응답 정상 |

---

## 6. 자주 나오는 이슈

- **401 Unauthorized:** 토큰이 안 넘어가거나 만료됨. 앱에서 토큰 재발급/재전송 확인.
- **연결 실패 / 타임아웃:** `API_BASE_URL` 이 정확한지, HTTPS인지, 방화벽/회사 네트워크 제한 없는지 확인.
- **Ingest 후 문서가 안 보임:** job이 실제로 처리되었는지 DB `jobs` / `sources` 상태와 `/worker/tick` 호출 여부 확인.
- **RAG 응답 이상:** 해당 문서가 embedding·chunk 저장되었는지, `documents` 등 테이블에서 확인.

이 문서는 `CLOUD_RUN_MIGRATION_PLAN.md` 10.7·10.8(스케줄러, Android E2E)과 함께 사용하면 된다.
