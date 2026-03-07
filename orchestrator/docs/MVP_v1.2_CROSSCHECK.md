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
| **8** | S2 Consolidation | ✅ 완료 | DB summaries(scope=topic, kind=S2), POST /jobs/s2, GET /s2, Cloud Scheduler(금 00:00 ET), Android Weekly Summary 탭(주별 카드·캐시·Re-process·상세) |
| **9** | Weekly Recommendation | ✅ 완료 | S2 job 내 arXiv Top 3 추천 생성, recommendations 테이블, GET/DELETE /recommendations, Android Recommendations 탭 실데이터(Process·Remove·필터) |
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
| POST /jobs/s2 | ✅ | S2 배치 트리거, week_start 지원, Cloud Scheduler 연동 |
| GET /s2 | ✅ | week_start, limit 쿼리. Android Weekly Summary에서 사용 |
| GET /recommendations | ✅ | week_start, topic_name, limit. Android Recommendations 탭 실데이터 |
| DELETE /recommendations/{id} | ✅ | 추천 1건 삭제(본인 소유). Process 후 삭제·Remove 버튼용 |
| (추천 생성) | ✅ | 별도 POST /jobs/recommendations 없음. S2 job 성공 직후 동일 run에서 arXiv Top 3 생성·INSERT, 실패 시 job은 성공·payload에 recommendations_failed |

추가로 구현된 것: DELETE /documents/{id}, POST /documents/{id}/reprocess, POST /me/trigger-worker, /health, /me.  
**Android:** Map → Weekly Summary(S2 실데이터). **Recommendations → 실데이터 연동 완료** (GET /recommendations, Process=ingest+삭제, Remove=삭제만, Time range·Topic 필터).

---

### MVP Week 9 vs 현재 구현 비교

| MVP 요구 | 현재 구현 | 일치 |
|----------|-----------|------|
| recommendations 테이블 | sql/52 적용, user_id·topic_name·week_start·title·abstract·url·source·score·created_at | ✅ |
| topic당 Top-3 저장 | S2 job 성공 후 run_arxiv_recommendations_for_week → 3건 INSERT (누적) | ✅ |
| GET /recommendations | GET /recommendations (week_start, topic_name, limit) | ✅ |
| Android에서 조회 | Recommendations 탭에서 실 API 호출, 카드·Process·Remove | ✅ |
| 후보 수집·embed·점수 | arXiv 검색 → S2 embedding으로 re-rank → Top 3 | ✅ (설계와 동일 방향) |
| POST /jobs/recommendations | 없음. S2 job 한 번에 S2+추천 수행 (설계상 선택 구현) | ✅ (계획대로) |

---

## 3. 다음 단계 제안 (우선순위)

### Option A — MVP v1.2 완주 (Week 8 → 9 → 10)

1. **Week 8 — S2 Consolidation** ✅ 완료
2. **Week 9 — Weekly Recommendation** ✅ 완료  
   - recommendations 테이블(52), S2 job 내 arXiv Top 3 생성·re-rank, GET/DELETE /recommendations, Android 실데이터 연동 완료.
3. **Week 10 — MVP Closure** ❌ 미진입
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
