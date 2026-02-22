# 로드맵: Usage Flow → Cloud Migration → Mobile UX

**목표:** 폰 하나로 관심 논문 ingest 후, 그 논문들에 대해 다양한 질문을 하며 쓰는 “문서 중심 연구 도구”.

---

## 현재 상태 (오늘까지 완료)

- **Firebase Auth E2E**  
  Android → FastAPI 실토큰 인증, `/me` → `firebase_uid`, DB `users` 1 row 매핑 확인.
- **Ingest 파이프라인**  
  job `done`까지 정상, chunk 생성·retrieval 동작 확인.
- **RAG 품질 이슈 원인 규명**  
  Retrieval 범위가 **user_id 아래 전체 chunk pool**이라,  
  “Summarize the document…”에서 **“the document”가 지정되지 않음** → 엉뚱한 문서/boilerplate chunk 혼입 → “I cannot answer…” 또는 부정확한 요약.

**핵심 결론 2개**

1. 인증/권한/ingest는 E2E로 붙었음 → Cloud migration 전제 충족.
2. RAG UX는 **“문서 범위 지정”**을 usage flow에 넣지 않으면 품질이 흔들림.

---

## 실행 순서 (3세션 가정)

| 순서 | 내용 | 이유 |
|------|------|------|
| **1** | **Usage Flow 설계 + 최소 API 변경** | 문서 범위 명확화 없이 Cloud 올리면 같은 문제가 그대로 올라감. |
| **2** | **Cloud Migration** | 안정된 로직을 api + worker, Cloud Run으로 이전. |
| **3** | **Mobile-first UX polishing** | Active document, 문서 전환 UI, 질문 히스토리 등. |

---

## Session 1 — Usage Flow + 최소 API

**목표**

- “폰에서 어떻게 쓰는지”를 완성형으로 정의.
- 문서 범위 모델 확정 → RAG 품질 구조 해결.

**해야 할 것**

1. **대표 시나리오 3개**
   - A) 방금 넣은 논문 요약  
   - B) 특정 논문에 대해 깊게 Q&A  
   - C) 내 전체 라이브러리 검색  

2. **문서 범위 모델**
   - **Active Document** (추천): 방금 ingest한 문서를 “현재 문서”로 자동 설정, 이후 질문은 `document_id` 생략 가능.  
   - 필요 시 **문서 선택 UI**로 전환.

3. **API/데이터 최소 변경**
   - **(A) `/rag/answer` 요청**
     - 현재: `{ query, top_k?, topic?, lang? }`  
     - 변경: `{ query, top_k?, document_id?, topic?, lang? }`  
     - `document_id` = 클라이언트 관점 “어떤 문서”. 서버/DB에서는 **`source_id`** (즉 `sources.id`)로 매핑.
   - **(B) `search_similar_chunks()`**
     - 현재: `WHERE s.user_id = %s` (+ topic, lang 옵션)  
     - 변경: `document_id`(source_id)가 있으면 `AND s.id = %s` 추가.

**DB/코드 참고**

- DB에는 **`document_id` 컬럼 없음**. **`sources.id`**가 문서 1개를 의미하고, `chunks.source_id`가 그 문서를 가리킴.
- API 필드명은 `document_id`(UX)로 두고, 내부적으로는 `source_id`(UUID)로 전달하면 됨.
- 실제 DB 스키마 덤프: `orchestrator/docs/db_schema_dump.json`. 로드맵과의 일치 검토 및 선택적 DDL: `orchestrator/docs/DB_ROADMAP_CONSISTENCY.md`.

**이 세션 끝나면**

- 문서 범위 명확.
- RAG 품질 구조 해결.
- 모바일 UX 방향 확정.

**구현 완료 (Session 1)**  
- `/rag/answer` 요청에 `document_id?` 추가 (UUID 검증).  
- `search_similar_chunks()` 에 `source_id` 옵션 추가.  
- LangGraph·direct 서비스 경로 모두 전달.

---

## Session 2 — Cloud Migration

- tick-driven worker, api + worker 2개 Cloud Run 서비스.
- Supabase / Firebase Admin 설정.
- Android base URL을 cloud endpoint로 변경.
- **목표:** LTE에서 E2E, 로컬 PC 의존 제거.

---

## Session 3 — Mobile-first UX polishing

- ~~최근 문서 자동 active 설정.~~ → **클라이언트 기준 “현재 문서”** 구현됨 (Feed에서 탭으로 선택, Ask에 document_id 전달). 서버 저장(active_document_id)은 미구현.
- **문서 전환 UI** ✅ Feed 카드 탭으로 선택, “Selected” 칩 + “Current document: …” 배너. 다른 카드 탭 시 전환.
- **질문 히스토리 per document, follow-up 질문** → 미구현 (추후).
- **목표:** “연구 도구”로 완성.

**오늘까지 Session 3에서 구현된 것**  
- Feed: 실제 문서 목록(5개 + Load more), 문서 선택 → 현재 문서 표시.  
- Ask: “Asking about: [제목]” 배너, RAG 요청 시 document_id 전달.  
- PDF/URL ingest 시 S1 요약(한 문장 + 3 포인트) 생성·저장, Feed 카드에 표시.

---

## 다음에 더 넣을 수 있는 것 (우선순위 순)

1. **Active document 개념**  
   - 예: `PATCH /session/active_document` 또는 user profile에 `active_document_id` 저장 → RAG 요청에서 `document_id` 생략 가능.
2. **Chunk 품질**  
   - Boilerplate(“abstract”, “download pdf”, “license”) 억제 또는 `chunk_type=content|boilerplate` 태깅 후 content만 검색.

---

## 다음 대화 시작용 컨텍스트 (복붙용)

```
Today we validated Firebase Auth real-token E2E (Android→FastAPI) and confirmed users(firebase_uid) single-row mapping, ingest jobs reach done, and retrieval returns chunks. RAG quality issue is structural: retrieval searches across all chunks in user's pool, so 'the document' is undefined unless we constrain by document_id/source_id. Next, design overall app usage flow to define document scope (active_document vs document picker vs topic/collection), then implement minimal API changes (RAG request document_id + search_similar_chunks filter by source_id), and plan Cloud Run migration (api+worker, tick-driven). DB uses source_id (sources.id); API can accept document_id and map to source_id.
```

---

## 빠른 테스트 시나리오 (Session 1 구현 후)

- 방금 ingest한 문서의 `source_id`를 얻어 `DOC_ID`로 설정.
- (A) 문서 지정 없이 `/rag/answer` 호출.
- (B) `"document_id": "<DOC_ID>"` 포함해서 동일 쿼리 호출.
- **기대:** (B)의 citations가 모두 같은 document, arXiv UI 같은 잡음 chunk 비율 감소.
