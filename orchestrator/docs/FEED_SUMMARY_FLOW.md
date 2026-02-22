# Feed 문서 카드 Summary — 현재 구현

Feed에서 document 카드를 로드할 때 summary(tldr, bullets)를 **어디서** 쓰는지 정리.

---

## 선택지 2가지 (개념)

| 방식 | 요약 |
|------|------|
| **A) Ingest 시 summary 생성 후 DB 저장** | Ingest 파이프라인에서 S1 요약을 만들고 `summaries` 테이블에 넣어 둠. Feed는 GET /documents 시 DB만 읽음. |
| **B) Load 시 RAG로 summary 생성 후 앱/서버에 저장** | 문서 목록 로드 시 RAG(또는 별도 요약 API)를 호출해 요약을 만들고, 그 결과를 앱 로컬/서버 캐시에 저장. |

---

## 현재 구현: **A (Ingest 시 DB 저장)** + 경로별 차이

- **Feed 로드 시**: RAG를 부르지 **않음**.  
  `GET /documents?include_summary=true` → `sources` LEFT JOIN `summaries`(scope='doc', kind='S1') 로 **이미 DB에 있는** tldr, bullets만 읽어서 반환.
- **Summary가 DB에 들어가는 시점**: **Ingest 시**에만.  
  단, **어떤 ingest 경로를 타느냐**에 따라 summary 생성 여부가 다름.

### 1) URL ingest (source_type = `"url"`)

- **진입**: `POST /ingest` (type=url) → job 생성 → **job_runner**가 처리.
- **실행**: `app.chains.ingest_graph` 사용  
  `fetch` → `persist` → `embed` → **`summarize_s1`** → END.
- **`summarize_s1`**:  
  - `fetch_top_chunks_for_summary(source_id)` 로 상위 N개 chunk 가져옴.  
  - `create_s1_summary(chunks_text)` (LLM) 로 tldr + bullets 생성.  
  - `repo.insert_summary_s1(...)` 로 **`summaries` 테이블에 저장**.
- **결과**: 이 경로로 ingest한 문서는 Feed에서 **summary 있음** (tldr, bullets 표시됨).

### 2) PDF ingest (source_type = `"pdf_url"`)

- **진입**: `POST /ingest` (type=pdf_url) → job 생성 → **job_runner**가 처리.
- **실행**: `app.worker.run_pdf_worker.process_one` 사용.  
  fetch PDF → parse → chunk → embed → persist (chunks + embeddings) → **S1 summary 생성** → mark_ready.
- **S1 summary**: persist 직후 `_create_s1_summary_for_source(user_id, source_id)` 호출.  
  `SupabaseRepo.fetch_top_chunks_for_summary` + `create_s1_summary`(LLM) + `insert_summary_s1` 로 **`summaries`에 저장**.  
  실패해도 PDF는 mark_ready 유지 (best-effort).
- **결과**: 이 경로로 ingest한 문서도 **`summaries`에 row가 있음** (정상 시). Feed에서 `include_summary=true` 시 tldr/bullets 표시됨.

---

## 요약 표

| 항목 | 현재 구현 |
|------|-----------|
| Feed가 summary를 가져오는 곳 | **DB만** (sources LEFT JOIN summaries). RAG/요약 API 호출 없음. |
| Summary가 DB에 들어가는 시점 | **Ingest 시** (URL·PDF 경로 모두). |
| URL ingest | ✅ **summary 생성 후 DB 저장** (ingest_graph → summarize_s1). |
| PDF ingest | ✅ **summary 생성 후 DB 저장** (process_one 내부에서 _create_s1_summary_for_source). |
| Load 시 RAG로 생성 후 앱/서버 저장 | ❌ **미구현**. |

---

이 문서는 “Feed document 카드 load 시 summary를 어떻게 했는지”에 대한 현재 구현 설명용이다.
