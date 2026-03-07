# S2 & Weekly Recommendation — 현재 상태 & 다음 스텝

`S2_AND_WEEKLY_RECOMMENDATION_DESIGN.md` 대비 구현/테스트 현황과 앞으로 할 일을 정리한다.

**최근 업데이트**: Weekly Recommendation BE·Android·DB 완료. S2 job 성공 시 arXiv Top 3 추천 생성, GET/DELETE /recommendations, Android Recommendations 탭 실데이터(Process·Remove·필터) 동작 확인. 로컬·Cloud 테스트 완료.

---

## 1. S2 Consolidation — 현재 상태

| 설계 항목 | 상태 | 비고 |
|-----------|------|------|
| **1.2 데이터 모델** | ✅ 완료 | `scope=topic`, `kind=S2`, `source_id=NULL`, `tldr`, `bullets`, `extra`(week_start, topic_name, source_ids) |
| **1.3.1 S2 배치 로직** | ✅ 완료 | 최근 7일 또는 `week_start` 지정 시 해당 주 구간 소스 → S1 조회 → LLM 1회 → insert. Idempotent(기존 S2 삭제 후 insert). Skip 시 job `error`에 사유 기록 |
| **1.3.2 트리거** | ✅ 완료 | `POST /jobs/s2`(body: optional week_start), job_type=s2, payload. Worker `process_job` s2 분기. `POST /worker/s2-schedule`(금요일 00:00 ET). **Cloud Scheduler job 등록 완료.** |
| **1.3.3 조회 API** | ✅ 완료 | `GET /s2` (query: week_start, limit) |
| **로컬 테스트** | ✅ 가능 | `S2_LOCAL_TEST.md` + Auth bypass + GET /me의 resolved_user_id로 유저 확인 |
| **Cloud Run 배포** | ✅ 완료 | S2 관련 BE 반영 후 이미지 빌드·배포 완료 |
| **1.4 단위/통합 테스트** | ⬜ 미구현 | S2 생성 함수 pytest (mock repo+LLM), 로컬 DB 통합 테스트 없음 |

**정리**: S2 BE 기능은 설계대로 동작 중. 테스트 코드만 추가하면 됨.

---

## 2. Weekly Recommendation — 현재 상태

| 설계 항목 | 상태 | 비고 |
|-----------|------|------|
| **2.2 데이터 모델** | ✅ 완료 | `recommendations` 테이블 (sql/52). user_id, topic_name, week_start, title, abstract, url, source, score, created_at |
| **2.3.1 파이프라인** | ✅ 완료 | S2 job 성공 직후 `run_arxiv_recommendations_for_week`: S2 텍스트→검색 쿼리→arXiv API→S2 embedding re-rank→Top 3 INSERT. 실패 시 job은 성공 유지·payload에 recommendations_failed |
| **2.3.2 트리거** | ✅ 완료 | 별도 POST /jobs/recommendations 없음. S2 job 한 번에 S2+추천 수행 (WEEKLY_RECOMMENDATION_PLAN 계획대로) |
| **2.3.3 조회·삭제 API** | ✅ 완료 | GET /recommendations (week_start, topic_name, limit), DELETE /recommendations/{id} |
| **2.4 테스트** | ✅ 수동 검증 | 로컬 uvicorn + Android(Cloud) 연동 확인. 단위/통합 pytest는 미구현 |

**정리**: Weekly Recommendation BE·Android·DB 구현 완료. 상세 계획·로컬 테스트 절차는 `WEEKLY_RECOMMENDATION_PLAN.md` §9 참고.

---

## 3. Android UX

| 항목 | 상태 | 비고 |
|------|------|------|
| S2 노출 | ✅ 완료 | 하단 네비 Weekly Summary 탭, 주별 카드·캐시·Re-process·Open. Cloud+앱 배포 완료. |
| Recommendations | ✅ 완료 | GET /recommendations 실데이터. 카드(title, abstract, 원문 링크), Process(ingest 후 삭제), Remove(삭제만), Time range·Topic 필터. |
| 주간 요약 생성 | ✅ 가능 | POST /jobs/s2 + trigger worker. 앱 Re-process. S2 성공 시 동일 run에서 추천 3건 생성. |

---

## 4. 앞으로 할 스텝 (우선순위 제안)

### 바로 할 수 있는 것 (선택)
- **S2 테스트 추가**
  - 단위: S2 생성 함수만 mock repo + mock LLM으로 검증 (scope=topic, kind=S2, bullets 개수 등).
  - 통합: 로컬 DB에 user + sources + S1 넣고 `run_s2_consolidation` 호출 → S2 row 1개 생성 확인.

### 완료된 기능 (참고)
- **Weekly Recommendation**: 마이그레이션(52), arXiv 추천 서비스, S2 job 내 호출, GET/DELETE /recommendations, Android 실데이터 연동 완료. 선택: 추천 파이프라인 단위/통합 pytest, RECOMMENDATIONS_USE_MOCK 옵션.

### 그 다음: MVP Closure (Week 10)
- 데모 시나리오 문서화·검증, 메트릭 스냅샷, Post-MVP 백로그.

---

## 5. 설계 문서 §4 API 요약 체크

| 메서드 | 경로 | 상태 |
|--------|------|------|
| POST | /jobs/s2 | ✅ |
| GET | /s2 | ✅ |
| GET | /recommendations | ✅ |
| DELETE | /recommendations/{id} | ✅ |
| (추천 생성) | S2 job 내부 | ✅ (별도 POST /jobs/recommendations 없음) |

Job 완료 확인: `GET /ingest/status?job_id=...` 사용 가능(단, s2 job은 별도 완료 확인).

---

## 6. 설계 문서 §5 로컬 체크리스트 요약
| 항목 | 상태 |
|------|------|
| S2 생성 함수 단위 테스트(mock repo + mock LLM) | ⬜ |
| S2 통합: 로컬 DB + S1 2~3개 → S2 1개 생성 검증 | ⬜ |
| 추천 파이프라인 후보 mock → Top-N 저장 검증 | ⬜ (수동 E2E로 대체) |
| RECOMMENDATIONS_USE_MOCK=true 등 설정으로 로컬 실행 | ⬜ (현재 실 arXiv 연동으로 로컬·Cloud 검증) |
| Android: Recommendations 화면 실데이터 바인딩 | ✅ |
| E2E: POST /jobs/s2 → GET /s2, S2 성공 시 추천 생성 → GET /recommendations | ✅ (로컬·Cloud 수동 검증 완료) |

---

**요약**: S2 Consolidation·Weekly Recommendation 모두 BE·Android·Cloud 배포 완료. S2 job 성공 시 arXiv Top 3 추천 자동 생성, 앱에서 Recommendations 탭으로 조회·Process·Remove·필터 가능. 남은 선택 작업: S2/추천 단위·통합 pytest, MVP Closure(Week 10).
