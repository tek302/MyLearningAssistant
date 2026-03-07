# Ingest 실패 시 참고 (404 / 403 / Medium 등)

## Medium 등에서 404 또는 403이 나는 이유

일부 사이트(Medium, 일부 뉴스/블로그)는 **서버에서 보내는 요청**을 봇으로 간주해 404 또는 403을 반환할 수 있습니다.

- **User-Agent가 너무 짧을 때**: 예전에는 `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36`만 보냈는데, `Chrome/xxx` 등이 없으면 “진짜 브라우저가 아님”으로 판단하는 CDN/보안 정책이 많습니다.
- **헤더가 부족할 때**: `Accept`, `Accept-Language` 등이 없으면 봇으로 분류될 수 있습니다.
- **요청 출처 IP**: Cloud Run 등 데이터센터 IP를 막는 사이트는 동일 URL이라도 브라우저에서는 200, 서버에서는 404를 줄 수 있습니다. **403**이면 데이터센터/봇 IP 차단일 가능성이 더 높습니다.

## 우리 쪽에서 한 조치

- **브라우저처럼 보이도록 헤더 보강** (`app/utils/web_fetch.py`):
  - User-Agent에 `Chrome/120.0.0.0 Safari/537.36` 포함
  - `Accept`, `Accept-Language` 추가
  - **Referer**: 요청 URL의 origin (예: `https://medium.com/`) 추가 — 일부 사이트가 Referer 없으면 403을 줌
- **404/403/실패 시 로그**: `url`, `status`, `final_url`을 warning 로그로 남김

**그래도 403이 나오면** (특히 Medium): **데이터센터 IP 차단** 가능성이 큽니다. 서버(Cloud Run)에서 해당 URL을 가져오는 것은 현재로선 어렵습니다. **사용자 측 대안**: 브라우저에서 해당 글을 연 뒤 "Print to PDF" 또는 "Save Page As"로 저장한 다음, (로컬 PDF ingest가 구현되면) 그 PDF를 앱에서 ingest.

이후에도 같은 Medium URL이 404라면:

1. **로컬에서 동일 URL로 테스트**:  
   `curl -I -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" "https://medium.com/google-cloud/..."`  
   → 404가 나오면 해당 사이트가 서버/봇 요청을 아예 막는 경우일 수 있음.
2. **대안**: 브라우저에서 “Print to PDF” 또는 “Read later” 확장으로 저장한 뒤, 그 PDF/HTML을 앱에서 ingest하는 방식 사용.
