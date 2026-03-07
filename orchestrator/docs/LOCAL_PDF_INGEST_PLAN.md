# Local PDF Ingest 추가 — 계획 (Plan Only)

**목표**: Feed 탭에서 URL 입력뿐 아니라 **로컬 PDF 파일**도 선택해서 ingest 할 수 있게 하기.

---

## 1. 현재 구조 요약

| 구분 | 현재 |
|------|------|
| **Android Feed** | `OutlinedTextField` "Enter URL" + Send → `IngestRepository.ingestUrl(url)` → `POST /ingest` (type=url 또는 pdf_url, content=URL 문자열) |
| **Backend POST /ingest** | `type`: url \| pdf_url \| text, `content`: 문자열만. PDF는 **URL**로만 받고, worker가 그 URL에서 PDF를 **다운로드**해서 처리. |
| **Worker** | `source_type=pdf_url` → URL에서 PDF fetch → PyMuPDF로 파싱 → chunk → embed → S1 저장. |

즉, **로컬 파일을 업로드하는 API와 파이프라인이 없음.**

---

## 2. 전체 흐름 (목표)

1. **앱**: 사용자가 "URL 입력" 또는 "파일 선택" 중 하나 선택 →  
   - URL: 기존처럼 `POST /ingest` (type=url/pdf_url, content=url).  
   - 파일: **파일 선택기**로 PDF 선택 → **업로드 API**로 파일 전송 → 응답으로 `job_id` 수신 → 기존과 동일하게 큐 잡으로 처리.
2. **Backend**:  
   - **파일 업로드 엔드포인트**에서 PDF 바이트 수신 → **저장소에 저장** (Supabase Storage 권장) → DB에 `sources` 행 생성 (로컬 PDF용 타입) → `jobs` 행 생성 → worker가 해당 소스를 **저장소에서 읽어서** 기존 PDF 파이프라인(파싱→chunk→embed→S1) 실행.  
   - **처리 완료 후** 해당 PDF 파일을 Storage에서 **삭제**하면 DB/Storage 용량이 쌓이지 않음 (§3.4.1).

---

## 3. Backend 계획

### 3.1 저장 위치

- **옵션 A — Supabase Storage**  
  - MVP 문서에 이미 "Storage (PDFs)" 언급됨.  
  - 버킷 하나 (예: `ingest-files`)에 `{user_id}/{source_id}.pdf` 형태로 저장.  
  - 업로드 후 `sources`에 `url` = Storage 공개 URL 또는 `meta.storage_path` 등으로 경로 저장.  
  - Worker는 해당 URL 또는 Storage SDK로 바이트 가져와서 기존 PyMuPDF 플로우에 넘김.
- **옵션 B — 서버 로컬 디스크 (임시)**  
  - Cloud Run은 무상태이므로 재시작 시 삭제됨. **로컬 개발/테스트**에서만 의미 있음.  
  - 프로덕션에서는 Storage가 필수이므로, **A를 기준으로 설계**하고 B는 로컬용 선택 보조로 둘 수 있음.

**권장**: **Supabase Storage**를 기본으로 설계. (이미 Supabase 사용 중이면 버킷·정책만 추가.)

### 3.2 소스 타입 및 스키마 (PDF 파일 업로드 방식일 때)

- **새 타입**: `source_type = 'pdf_file'` (또는 기존 `pdf_url`과 구분만 되면 됨).
- **sources 테이블**:  
  - `url`: 로컬 PDF의 경우 **Storage의 공개 URL** 또는 빈 값 + `meta`에 경로.  
  - `meta`: 예) `{"storage_path": "user_id/source_id.pdf", "original_filename": "article.pdf"}`.  
  - 기존 `pdf_url`은 그대로 URL 문자열만 있으면 됨.

### 3.3 새 API

- **POST /ingest/file** (또는 **POST /ingest**에 multipart 지원 추가)
  - **Content-Type**: `multipart/form-data`.
  - **필드**: `file` (PDF 파일), 선택 `title` (파일명 또는 사용자 입력).
  - **동작**:  
    1. 파일 크기 제한 검사 (예: 25MB, 기존 PDF 제한과 동일).  
    2. user_id 확인 (기존 인증 의존성 재사용).  
    3. Storage에 업로드 → `source_id` 생성, `sources`에 `source_type=pdf_file`, `url` 또는 `meta.storage_path` 설정.  
    4. `jobs`에 ingest job 생성.  
    5. 응답: `{ "job_id": "...", "status": "queued" }` (기존 POST /ingest와 동일 형태).
  - **에러**: 413 (파일 너무 큼), 400 (PDF 아님 또는 빈 파일), 401/403 (인증).

### 3.4 Worker 확장

- **job_runner**: `source_type == 'pdf_file'`인 경우, **URL fetch 대신** Storage에서 바이트를 가져오는 경로로 분기.
- **run_pdf_worker** (또는 공통 PDF 처리 함수):  
  - 입력이 "URL"이면 기존처럼 `requests.get(url)` → 바이트.  
  - 입력이 "Storage 경로/URL"이면 Supabase Storage API로 바이트 가져오기 → 이후 **동일**: PyMuPDF 파싱 → chunk → embed → S1 → DB 저장.  
- **중복 제거**: PDF 바이트만 넘기면 되는 공통 함수 `process_pdf_bytes(pdf_bytes, source_id, user_id, title?)` 같은 형태로 정리하면, `pdf_url`과 `pdf_file`이 같은 파이프라인을 타게 할 수 있음.

### 3.4.1 처리 완료 후 PDF 삭제 (Storage 용량 유지) — **권장**

앱에서 PDF 파싱 시 **소요 시간·추출 품질**이 부담된다면, **PDF는 업로드해서 서버에서만 파싱**하고, **ingest가 끝난 뒤에는 PDF 파일만 지우는** 방식이 적합하다.

- **흐름**: 앱 → PDF 업로드 (multipart) → Storage에 저장 → Worker가 Storage에서 PDF 읽어 PyMuPDF로 파싱 → chunk → embed → S1 저장 → **같은 job 처리 끝난 직후 해당 Storage 객체(PDF 파일) 삭제**.
- **결과**: 서버에서 기존 PyMuPDF 파이프라인을 그대로 쓰므로 품질·속도 문제 없음. 앱은 PDF 라이브러리 불필요. Storage에는 PDF가 **임시로만** 있고, 처리 완료 후 삭제되므로 **용량이 계속 쌓이지 않음**. DB에는 여전히 chunks + embeddings + summaries만 남음.
- **구현 요지**: Worker에서 `pdf_file` 소스 처리 후, `process_pdf_bytes`(또는 동일 플로우) 성공 시 **Storage API로 해당 경로 객체 삭제** 호출. 실패(예: 파싱 실패) 시에는 PDF를 남겨 두어 재시도나 디버깅에 쓸지, 정책에 따라 삭제할지 선택 가능(기본은 성공 시에만 삭제 권장).
- **에러 처리**: 삭제 실패해도 job은 이미 done 처리했으므로 로그만 남기고 넘어가면 됨. 필요하면 재시도 또는 수동 정리.

이렇게 하면 **§3.5(앱에서 텍스트 추출)** 의 단점(파싱 시간·품질)을 피하면서, **§3.1~3.4(업로드)** 의 단점(Storage 증가)도 피할 수 있다. **로컬 PDF ingest의 기본 권장**으로 두기 좋다.

---

## 3.5 대안: PDF 원본 없이 Summary + Chunk만 저장 (앱에서 텍스트 추출)

PDF 바이트를 **어디에도 저장하지 않고**, **추출된 텍스트 → chunk + embedding + S1 summary**만 서버에 두는 방식이다.

**아이디어**
- **앱**: 로컬 PDF를 기기에서 **텍스트로만 추출** → 그 **텍스트**만 `POST /ingest` (type=text, content=추출 텍스트, title=파일명)로 전송.
- **백엔드**: PDF 파일/Storage 없음. sources에 원문을 잠깐만 보관할 컬럼(예: `raw_text`) 사용.
- **Worker**: source_type=text 처리 — raw_text 읽어서 chunk → embed → S1 생성 후 **raw_text를 NULL로** 만들어 원문 삭제. 결과적으로 **chunks + embeddings + summaries**만 DB에 남음.

**장점**: PDF 원본이 DB/Storage 어디에도 없어서 용량이 거의 안 늘어남. 기존 type=text API 확장 + Worker 분기만 추가하면 됨.  
**단점**: 앱에서 PDF 파싱 라이브러리 필요. 이미지/표가 많은 PDF는 텍스트 추출 품질이 떨어질 수 있음.

**Backend**: sources에 `raw_text`(또는 meta 내 보관) 컬럼 추가 → Worker가 type=text일 때 이걸 읽어 chunk/embed/S1 후 raw_text 비우기.  
**Android**: SAF로 PDF 선택 → 기기에서 텍스트 추출 (PdfRenderer, PdfBox-Android 등) → POST /ingest (type=text, content=..., title=...) 호출.

앱 파싱이 부담이면 **§3.4.1(업로드 후 처리 완료 시 PDF 삭제)** 를 쓰고, 원본을 서버에 아예 안 올리고 싶을 때만 이 방식(앱 텍스트 추출)을 선택하면 된다.

---

### 3.6 정리 (Backend) — PDF 파일 업로드 방식 (§3.1~3.4)

| 항목 | 내용 |
|------|------|
| 저장소 | Supabase Storage (버킷 + 경로 규칙). |
| source_type | `pdf_file` 추가, `url` 또는 `meta.storage_path`로 Storage 위치 참조. |
| API | POST /ingest/file (multipart), 응답은 기존과 동일 job_id. |
| Worker | pdf_file → Storage에서 PDF 바이트 로드 → 기존 PDF 처리 플로우. |

---

## 4. Android 계획

### 4.1 Feed UI 변경 (개념)

- **현재**: "Enter URL" 한 줄 + Refresh + Send.
- **목표**:  
  - **같은 입력 영역**에서 "URL도 넣고, 로컬 파일도 고를 수 있게".
  - 제안:
    - **방안 1**: 입력창은 그대로 두고, 옆에 **"파일 선택"** 버튼(아이콘) 추가.  
      - URL 입력 후 Send → 기존 URL ingest.  
      - "파일 선택" → 파일 선택기(SAF) → PDF 선택 → 업로드 API 호출 → job_id 받으면 기존처럼 "Queued…" 스낵바 + 목록 새로고침.
    - **방안 2**: 탭 또는 드롭다운으로 "URL" / "파일" 전환.  
      - URL 탭: 기존 UI.  
      - 파일 탭: "파일 선택" 버튼만 있거나, 선택한 파일명 표시 후 "업로드" 버튼.
  - **권장**: **방안 1**. 한 화면에서 URL 입력과 파일 선택을 모두 할 수 있어서 단순함.

### 4.2 파일 선택

- **Storage Access Framework (SAF)** 사용: `Intent.ACTION_GET_CONTENT` (또는 `ACTION_OPEN_DOCUMENT`), `type = "application/pdf"`.  
  - 사용자가 기기/드라이브에서 PDF를 고르면 `Uri` 반환.
- **권한**: 외부 저장소 권한 없이도 SAF로 선택한 파일의 `Uri`를 **ContentResolver**로 읽을 수 있음 (일회성 읽기 권한).

### 4.3 업로드

- **Retrofit**에서 `multipart/form-data`:  
  - `RequestBody` 또는 `MultipartBody.Part`로 PDF 바이트(또는 `Uri`에서 읽은 스트림) 전달.  
  - 필드명: `file`, 선택 `title`.  
- **엔드포인트**: `POST /ingest/file` (Backend에서 정의한 경로와 일치시키기).
- **응답**: `job_id`, `status` → 기존과 동일하게 "Queued for ingest", `loadPage(0)` 호출.

### 4.4 진행 표시

- 파일이 크면 업로드 시간이 길어질 수 있음.  
  - **옵션**: `OkHttp`에 `ProgressListener`를 붙여서 업로드 % 표시 (선택).  
  - 최소한 "Uploading…" 스피너 또는 인디케이터는 표시하는 것이 좋음.

### 4.5 에러 처리

- 413 (파일 큼): "File is too large (max 25MB)."  
- 400: "Not a valid PDF" 등.  
- 네트워크 오류: 기존과 동일하게 스낵바 메시지.

### 4.6 정리 (Android)

| 항목 | 내용 |
|------|------|
| UI | Feed 상단에 "파일 선택" 버튼 추가 (URL 입력 + Send는 유지). |
| 선택 | SAF, type=application/pdf, Uri → 바이트 읽기. |
| 업로드 | Retrofit multipart POST /ingest/file, job_id 응답. |
| 이후 | 기존과 동일: job_id로 큐 잡, 목록 새로고침, Process/status는 그대로. |

---

## 5. 테스트 계획 (참고)

- **Backend**
  - 단위: Storage 업로드 모듈 mock, `sources`/`jobs` insert 검증.
  - 통합: multipart로 작은 PDF 보내서 `pdf_file` 소스 + job 생성 → worker가 Storage에서 읽어 처리 완료까지 (로컬 또는 테스트 DB).
- **Android**
  - 단위: Repository에서 multipart 요청 빌드 및 mock 응답 처리.
  - 수동: 실제 기기에서 PDF 선택 → 업로드 → Feed에 문서 나타나는지, RAG에서 사용 가능한지 확인.

---

## 6. 구현 순서 제안

1. **Backend**
   - Supabase Storage 버킷 생성 및 정책 (업로드/읽기).
   - `POST /ingest/file` (multipart) 구현: 크기 제한, Storage 업로드, `sources`(pdf_file) + `jobs` 생성.
   - Worker 확장: `pdf_file`일 때 Storage에서 PDF 바이트 로드 후 기존 PDF 처리 플로우 호출.
2. **Android**
   - IngestApi에 `ingestFile(file: MultipartBody.Part, title: String?)` 추가.
   - IngestRepository에 `ingestPdfFile(uri: Uri)` (또는 바이트 + 파일명) 추가.
   - FeedScreen: "파일 선택" 버튼 + SAF + 업로드 호출 + 스낵바/로딩.
3. **테스트**
   - 로컬에서 작은 PDF로 E2E (앱 → Backend → Worker → Feed 반영).

---

## 7. 요약

| 레이어 | 변경 요약 |
|--------|-----------|
| **Backend** | **(권장)** PDF 업로드 → Storage → Worker가 파싱·chunk·embed·S1 후 **해당 PDF 파일 Storage에서 삭제** (§3.4.1). **(A)** 원본 보관이 필요하면 삭제 생략. **(B)** 앱에서 텍스트만 추출: type=text + raw_text(처리 후 삭제). |
| **Android** | **(권장·A)** Feed에 "파일 선택", SAF로 PDF 선택, multipart 업로드. **(B)** SAF → 기기에서 텍스트 추출 → POST /ingest (type=text). |
| **테스트** | Backend multipart + worker 분기 + 처리 후 Storage 삭제 검증; Android 수동 E2E. |

**권장**: **업로드 후 ingest 완료 시 PDF만 삭제** (§3.4.1) — 서버 PyMuPDF 품질·속도 유지, Storage 용량 불증가, 앱에서 PDF 파싱 불필요.
