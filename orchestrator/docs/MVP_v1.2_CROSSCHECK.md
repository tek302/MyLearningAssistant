# Learning Assistant MVP v1.2 — Cross-Check & Next Steps

**기준 문서:** `Learning_Assistant_MVP_v1.2.md` (root)  
**기준 시점:** v0.9-week8 태그 기준.

---

## 1. MVP v1.2 대비 현재 상태 요약

| Week | MVP 범위 | 현재 상태 | 비고 |
|------|----------|-----------|------|
| **1–2** | Ingest & S1 | ✅ 완료 | URL/PDF ingest, chunk/embed, S1(tldr,bullets), idempotent |
| **3** | RAG v1 | ✅ 완료 | POST /rag/answer, pgvector, document_id 스코프 |
| **4** | Quality Guard & Refine | ✅ 구현됨 | rule-based eval, LLM judge, refine loop (graphs) |
| **5** | Android Minimal | ✅ 완료 | Firebase auth, Android→Cloud→RAG, URL/PDF ingest |
| **6** | Usability & Integration | ✅ 완료 | POST /ingest→job_id, GET /ingest/status, GET /documents(=feed), worker/tick, 앱에서 Process/Re-process |
| **7** | Cloud E2E Pilot | ✅ 완료 | Cloud Run 배포, Android→Cloud E2E, ANDROID_CLOUD_E2E.md |
| **8** | S2 Consolidation | ⚠️ 미구현 | DB에는 summaries(scope=topic, kind=S2) 스키마 있음. **배치 S2 생성 job/API 없음** |
| **9** | Weekly Recommendation | ❌ 미구현 | 파이프라인 없음. Android Recommendations 화면은 Fake 데이터. 후보/추천 테이블 없음 |
| **10** | MVP Closure | ❌ 미진입 | 데모 시나리오 정리, 메트릭 스냅샷, Post-MVP 백로그 미작성 |

---

## 2. API 대비 (MVP §2 “Canonical MVP Architecture”)

| MVP 문서 | 현재 구현 | 비고 |
|----------|-----------|------|
| POST /ingest | ✅ | job_id 반환 |
| GET /ingest/status | ✅ | job_id로 state 조회 |
| GET /sources | ✅ | GET /documents 로 구현 (S1 포함) |
| GET /feed | ✅ | GET /documents + include_summary 로 동일 역할 |
| POST /rag/answer | ✅ | document_id 선택 지원 |
| POST /jobs/s2 | ❌ | S2 배치 트리거 없음 |
| POST /jobs/recommendations | ❌ | 주간 추천 파이프라인 없음 |

추가로 구현된 것: DELETE /documents/{id}, POST /documents/{id}/reprocess, POST /me/trigger-worker, /health, /me.

---

## 3. 다음 단계 제안 (우선순위)

### Option A — MVP v1.2 완주 (Week 8 → 9 → 10)

1. **Week 8 — S2 Consolidation**
   - **백엔드:** S2 배치 job (일/주 단위). 입력: 최근 S1 + (선택) notes + 이전 S2. topic 단위, scope=’topic’, kind=’S2’.
   - **트리거:** POST /jobs/s2 또는 스케줄러에서 호출하는 내부 엔드포인트.
   - **Exit:** 5~20개 토픽, 재생성 시 idempotent.

2. **Week 9 — Weekly Recommendation**
   - **스키마:** candidates / recommendations / rec_feedback 테이블 추가 (필요 시).
   - **파이프라인:** S2 토픽 열거 → 쿼리 확장 → 후보 수집(arXiv/RSS 등) → embed+점수 → topic당 Top-3 → 저장.
   - **API:** GET /recommendations 또는 기존 Android Recommendations를 실데이터로 연동.
   - **Exit:** topic당 Top-3, Android에서 조회 가능.

3. **Week 10 — MVP Closure**
   - 데모 시나리오 3가지 문서화 및 검증 (PDF→질의→답변, 다중 doc→S2, 주간 추천 노출).
   - latency / refine rate / cannot-answer rate 등 메트릭 스냅샷.
   - Post-MVP 백로그 정리.

### Option B — S2/Recommendation 없이 MVP “실사용” 마무리

- Week 8–9를 나중으로 미루고, **현재 기능만으로** 데모 시나리오(예: PDF ingest → RAG, Re-process로 제목/요약 갱신) 고정.
- 문서: “MVP v1.2 중 Week 7까지 완료. Week 8–9는 Phase 2로 이관.”
- Android Notes/Map/Recommendations는 “Coming soon” 또는 Fake 유지.

### Option C — 한 단계만 진행

- **S2만 먼저:** S2 배치 job + scope=’topic’/kind=’S2’ 저장. 추천은 이후.
- 또는 **Recommendation만:** S2 없이 고정 토픽/키워드로 후보 수집 + Top-3 API만 구현 (MVP와는 약간 다른 스코프).

---

## 4. 권장 방향

- **목표가 “MVP v1.2 Canonical Statement까지 완주”**라면 → **Option A** 순서(Week 8 → 9 → 10) 추천.
- **목표가 “실제로 쓸 수 있는 최소 버전 빠르게”**라면 → **Option B**로 정리하고, S2/Recommendation은 별도 이슈로 분리.

이 문서는 `Learning_Assistant_MVP_v1.2.md`와 함께 보면서 주간 단위로 체크해 보시면 됩니다.
