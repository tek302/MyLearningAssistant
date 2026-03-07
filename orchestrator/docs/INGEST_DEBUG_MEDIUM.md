# Medium / URL Ingest 실패 시 디버깅

Cloud Run에 배포 후 특정 URL(예: Medium) ingest가 실패할 때, **어디서** 막혔는지 확인하는 방법.

---

## 1. 실패한 job의 에러 메시지 확인 (가장 먼저)

Ingest를 시도하면 `POST /ingest` 응답에 `job_id`가 온다. 그 job이 실패하면 **에러 메시지가 DB에 저장**된다.

### 앱에서 job_id를 모를 때

- 앱에서 URL 넣고 Send → "Queued" 후 Process(또는 자동 tick) 되면, **가장 최근에 실패한 job**이 그 URL일 가능성이 높다.
- **GET /ingest/status** 로 확인하려면 `job_id`가 필요하다.  
  - 앱이 job_id를 저장/표시하지 않는다면: **Cloud Run 로그**에서 `job_id`를 찾거나(§2), **DB에서** 최근 실패한 job을 조회한다.

### job_id를 알고 있을 때

```bash
# Bearer 토큰 필요 (Firebase ID token 등)
curl -s -H "Authorization: Bearer YOUR_TOKEN" \
  "https://YOUR-CLOUD-RUN-URL/ingest/status?job_id=JOB_UUID"
```

응답 예:

```json
{
  "state": "failed",
  "progress": 10,
  "source_id": "...",
  "error": "404 Client Error: Not Found for url: https://medium.com/..."
}
```

- **error** 필드에 **HTTP 상태 코드**와 **실제 요청된 URL**(리다이렉트 후일 수 있음)이 들어 있다.  
  - `404` → 서버가 해당 요청을 거부했거나 리소스 없음.  
  - `403` → 봇/권한 차단 가능성.  
  - `Timeout` 등 → 네트워크/타임아웃 이슈.

---

## 2. Cloud Run 로그에서 확인할 것

GCP 콘솔 → **Cloud Run** → 해당 서비스 → **Logs** 탭.

### 검색 키워드 (로그 필터)

- `job_id` — 실패한 job의 UUID. `url ingest failed` 또는 `worker_tick: claimed job_id=...` 로 같은 job_id가 보이면 그게 해당 job.
- **HTML fetch failed** — `web_fetch`에서 4xx/5xx일 때 남기는 warning.  
  - 로그 메시지: `url=... status=... final_url=...`  
  - **final_url**이 원래 URL과 다르면 리다이렉트된 주소다 (Medium이 다른 페이지로 보냈을 수 있음).
- **url ingest failed** — `job_runner`에서 URL ingest 예외 발생 시. 바로 아래에 Python traceback과 **예외 메시지**가 있다 (예: `404 Client Error: Not Found for url: ...`).

### 로그 순서 (URL ingest 실패 시)

1. `worker_tick: claimed job_id=...`
2. (실패 시) `HTML fetch failed: url=... status=404 final_url=...` (같은 요청)
3. `job_id=... url ingest failed: ...` + traceback

**status**와 **final_url**을 보면, 헤더 부족인지·리다이렉트인지·IP 차단인지 추론할 수 있다.

---

## 3. DB에서 직접 확인 (선택)

Supabase 대시보드 또는 `psql`:

```sql
-- 최근 실패한 ingest job (에러 메시지 포함)
SELECT id, state, error, source_id, created_at
FROM jobs
WHERE job_type = 'ingest' AND state = 'failed'
ORDER BY created_at DESC
LIMIT 5;
```

```sql
-- 해당 source의 상태 (source_id는 위 결과에서)
SELECT id, url, source_type, status, fail_code
FROM sources
WHERE id = 'SOURCE_UUID';
```

- **jobs.error**: fetch 단계에서 나온 예외 메시지 (예: 404, timeout).  
- **sources.status**: `failed` 이고 **sources.fail_code** 가 있으면 PDF worker에서 실패한 경우; URL ingest는 보통 **job.error**만 채워진다.

---

## 4. 원인 구분

| 현상 | 가능 원인 | 다음 단계 |
|------|-----------|-----------|
| **error에 404**, final_url이 원래 URL과 같음 | 해당 URL이 서버 요청에 대해 404 반환 (Medium 등이 봇/비브라우저로 판단) | §5 헤더/curl 확인 |
| **error에 404**, final_url이 다른 URL (로그인/캡차 등) | 리다이렉트됨. Medium이 로그인/캡차 페이지로 보냈을 수 있음 | 동일. 또는 해당 사이트는 서버 ingest 비지원으로 간주 |
| **error에 Timeout** | 네트워크 지연 또는 상대 서버 응답 느림 | 타임아웃 증가(`web_fetch` timeout), 또는 나중에 재시도 |
| **error에 403** | 봇 차단 또는 지역/IP 제한 | §5. 사이트가 데이터센터 IP 차단하면 Cloud Run에서만 실패할 수 있음 |

---

## 5. PC에서 동일 요청 재현 (curl)

Cloud Run이 **데이터센터 IP**라서 막히는지, 아니면 **헤더만** 문제인지 구분하려면, **같은 헤더**로 PC에서 요청해 본다.

```bash
# 우리가 쓰는 User-Agent와 비슷하게
curl -I -L \
  -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
  -H "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8" \
  -H "Accept-Language: en-US,en;q=0.9" \
  "https://medium.com/google-cloud/integrate-notebooklm-with-gemini-cli-..."
```

- **PC에서 200** 이 나오고 **Cloud Run에서는 404** → Medium이 **Cloud Run IP 대역을 막는** 것일 수 있음. 이 경우 서버에서 해당 URL을 ingest하는 것은 어렵고, 사용자에게 "이 링크는 서버에서 가져올 수 없습니다. 브라우저에서 PDF로 저장한 뒤 PDF를 추가해 주세요" 같은 안내가 필요.
- **PC에서도 404** → 헤더를 더 보강해 보거나(Referer 등), 해당 글이 삭제/이전되었을 수 있음.

---

## 6. 체크리스트 요약

1. [ ] **GET /ingest/status?job_id=...** 로 **error** 확인 (또는 DB `jobs.error`).
2. [ ] **Cloud Run Logs**에서 해당 `job_id` / **HTML fetch failed** / **url ingest failed** 로그 확인 → **status**, **final_url** 확인.
3. [ ] 필요 시 **DB**에서 `jobs` + `sources` 상태·fail_code 확인.
4. [ ] **curl**로 같은 URL·같은 헤더를 PC에서 요청 → 200이면 IP 차단 가능성, 404면 헤더/페이지 이슈.

이 순서대로 보면 실패 원인을 좁혀갈 수 있다.
