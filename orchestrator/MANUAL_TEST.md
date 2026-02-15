# 수동 테스트 가이드 (PowerShell)

## 1. 서버 실행

터미널 1에서:

```powershell
cd orchestrator
.\.venv\Scripts\Activate.ps1
$env:AUTH_BYPASS_USER_ID = "dev-user"
uvicorn app.main:app --reload
```

서버가 `http://127.0.0.1:8000`에서 실행됩니다. **Week6:** 단일 프로세스만 필요합니다 (별도 PDF worker 불필요).

---

## Week6 E2E 테스트 (curl / PowerShell)

PC에서 Android 없이 전체 플로우: POST /ingest → poll /ingest/status → POST /rag/answer → GET /documents.

### 1) POST /ingest (pdf_url 또는 url)

**curl (Windows PowerShell):**

```powershell
$env:AUTH_BYPASS_USER_ID = "dev-user"
curl -s -X POST "http://127.0.0.1:8000/ingest" `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer dev-user" `
  -d '{\"type\":\"pdf_url\",\"content\":\"https://arxiv.org/pdf/1706.03762.pdf\"}'
```

또는 URL 타입:

```powershell
curl -s -X POST "http://127.0.0.1:8000/ingest" `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer dev-user" `
  -d '{\"type\":\"url\",\"content\":\"https://en.wikipedia.org/wiki/FastAPI\"}'
```

**예상 응답:** `{"job_id":"<uuid>","status":"queued"}`

### 2) Poll GET /ingest/status?job_id=...

`<job_id>`를 위 응답의 job_id로 교체:

```powershell
curl -s "http://127.0.0.1:8000/ingest/status?job_id=<job_id>" -H "Authorization: Bearer dev-user"
```

**예상 응답 (진행 중):** `{"state":"running","progress":10,"source_id":"<uuid>","error":null}`  
**완료 시:** `{"state":"done","progress":100,"source_id":"<uuid>","error":null}`  
**실패 시:** `{"state":"failed","progress":0,"source_id":"<uuid>","error":"..."}`  

개발 환경에서 ingest 완료 기준: **60초 이내**에 `state: "done"` 도달.

### 3) POST /rag/answer

```powershell
curl -s -X POST "http://127.0.0.1:8000/rag/answer" `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer dev-user" `
  -d '{\"query\":\"What is attention in transformers?\",\"top_k\":5}'
```

**성공 기준:** `citations` 배열 길이 >= 1.

### 4) GET /documents

```powershell
curl -s "http://127.0.0.1:8000/documents" -H "Authorization: Bearer dev-user"
```

**예상:** `documents` 배열에 방금 ingest한 소스가 있고, `status`가 `"done"`이며, 필요 시 `updated_at` 포함.

---

## 2. 데이터 Ingest (먼저 실행)

Week6부터는 **POST /ingest**로 job을 넣고 **GET /ingest/status?job_id=...** 로 완료를 기다립니다. 위 "Week6 E2E 테스트" 참고.

PowerShell 예시 (POST /ingest → job_id 받기):

```powershell
$env:AUTH_BYPASS_USER_ID = "dev-user"
$r = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/ingest" `
  -ContentType "application/json" `
  -Headers @{ Authorization = "Bearer dev-user" } `
  -Body (@{ type = "url"; content = "https://en.wikipedia.org/wiki/FastAPI" } | ConvertTo-Json -Compress)
$r.job_id   # poll /ingest/status?job_id=$r.job_id until state is done
```

**응답 예시:** `{ "job_id": "<uuid>", "status": "queued" }`

## 3. RAG Answer 테스트

같은 터미널(터미널 2)에서:

### 기본 쿼리:

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/rag/answer" `
  -ContentType "application/json" `
  -Body (@{ 
    query = "What is FastAPI?"
    top_k = 5
  } | ConvertTo-Json -Compress) | ConvertTo-Json -Depth 10
```

### 필터 포함 쿼리 (topic, lang):

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/rag/answer" `
  -ContentType "application/json" `
  -Body (@{ 
    query = "What is FastAPI?"
    top_k = 8
    topic = "web-frameworks"
    lang = "en"
  } | ConvertTo-Json -Compress) | ConvertTo-Json -Depth 10
```

### 결과 없음 테스트:

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/rag/answer" `
  -ContentType "application/json" `
  -Body (@{ 
    query = "xyzabc123nonexistentquery987654321"
    top_k = 5
  } | ConvertTo-Json -Compress) | ConvertTo-Json -Depth 10
```

**응답 예시:**
```json
{
  "answer": "FastAPI is a modern web framework for building APIs with Python [1]. It is based on standard Python type hints [2].",
  "citations": [
    {
      "citation_number": 1,
      "chunk_id": "550e8400-e29b-41d4-a716-446655440000",
      "source_id": "660e8400-e29b-41d4-a716-446655440001",
      "url": "https://en.wikipedia.org/wiki/FastAPI",
      "title": "FastAPI",
      "chunk_index": 1,
      "score": 0.85,
      "quote": "FastAPI is a modern web framework..."
    }
  ],
  "meta": {
    "top_k": 5,
    "latency_ms": 1234,
    "model": "gpt-4o-mini"
  }
}
```

## 4. Health Check

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health"
```

## 5. 에러 테스트

### 빈 쿼리 (422 에러):

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/rag/answer" `
  -ContentType "application/json" `
  -Body (@{ query = "" } | ConvertTo-Json -Compress)
```

### 잘못된 top_k (422 에러):

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/rag/answer" `
  -ContentType "application/json" `
  -Body (@{ 
    query = "test"
    top_k = 100
  } | ConvertTo-Json -Compress)
```

## 문제 해결 (Troubleshooting)

### 에러: `[Errno 11001] getaddrinfo failed`

이 에러는 DNS 조회 실패를 의미합니다. 다음을 확인하세요:

#### 1. 환경 변수 확인

`.env` 파일이 `orchestrator/` 디렉토리에 있고, 다음 변수들이 설정되어 있는지 확인:

```powershell
# orchestrator/.env 파일 확인
Get-Content .env
```

필수 변수:
- `SUPABASE_DB_URL` - PostgreSQL 연결 문자열 (예: `postgresql://user:pass@host:port/dbname`)
- `OPENAI_API_KEY` - OpenAI API 키
- `AUTH_BYPASS_USER_ID=dev-user` (테스트용)

#### 2. Supabase DB 연결 테스트

```powershell
# Python으로 직접 연결 테스트
python -c "import os; from dotenv import load_dotenv; import psycopg; load_dotenv(); conn = psycopg.connect(os.getenv('SUPABASE_DB_URL')); print('DB 연결 성공!'); conn.close()"
```

**에러: `[Errno 11001] getaddrinfo failed` 또는 `Non-existent domain`**

이 에러는 Supabase 호스트 이름을 DNS에서 찾을 수 없다는 의미입니다. 다음을 확인하세요:

1. **Supabase 프로젝트 상태 확인 (가장 흔한 원인!):**
   - Supabase 대시보드 (https://supabase.com/dashboard)에 로그인
   - 프로젝트가 **Active** 상태인지 확인
   - 프로젝트가 일시 중지(paused)되었거나 삭제되었는지 확인
   - **일시 중지된 경우: 대시보드에서 "Resume" 버튼을 클릭하여 프로젝트를 재시작하세요**

2. **올바른 DB URL 확인:**
   - Supabase 대시보드 → Settings → Database
   - **Connection string** 섹션에서 올바른 호스트 이름 확인
   - 형식: `postgresql://postgres:[PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres`
   - `.env` 파일의 `SUPABASE_DB_URL`이 올바른지 확인

3. **호스트 이름 직접 확인:**
   ```powershell
   # DNS 조회 테스트
   nslookup db.[YOUR-PROJECT-REF].supabase.co
   
   # 네트워크 연결 테스트
   Test-NetConnection -ComputerName db.[YOUR-PROJECT-REF].supabase.co -Port 5432
   ```

4. **프로젝트 재시작:**
   - Supabase 프로젝트가 일시 중지된 경우, 대시보드에서 재시작
   - 프로젝트가 삭제된 경우, 새 프로젝트를 생성하고 새로운 DB URL 사용

#### 3. 인터넷 연결 확인

```powershell
# Wikipedia 접근 테스트
Invoke-WebRequest -Uri "https://en.wikipedia.org/wiki/FastAPI" -UseBasicParsing | Select-Object StatusCode
```

#### 4. 서버 로그 확인

서버를 실행한 터미널에서 더 자세한 에러 메시지를 확인하세요. 에러가 발생한 단계를 확인할 수 있습니다:
- `node_fetch`: URL 가져오기 실패
- `node_persist`: DB 연결 실패

#### 5. 방화벽/프록시 확인

회사 네트워크나 방화벽이 Supabase 호스트나 Wikipedia를 차단하는지 확인하세요.

## 주의사항

1. **환경 변수**: `.env` 파일에 다음이 설정되어 있어야 합니다:
   - `OPENAI_API_KEY`
   - `SUPABASE_DB_URL`
   - `AUTH_BYPASS_USER_ID=dev-user` (테스트용)

2. **순서**: RAG 테스트 전에 POST /ingest로 데이터를 넣고, GET /ingest/status로 완료될 때까지 기다린 뒤 진행합니다.

3. **대기 시간**: Ingest 후 embedding이 완료될 때까지 1-2초 정도 기다려야 할 수 있습니다.

4. **JSON 포맷팅**: PowerShell에서 JSON을 보기 좋게 보려면 `| ConvertTo-Json -Depth 10`을 추가하세요.

