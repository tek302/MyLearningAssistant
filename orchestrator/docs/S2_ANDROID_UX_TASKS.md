# S2 Summary ↔ Android UX 연동 작업 정리

**목표**: 하단 네비의 "Map"을 "Weekly Summary"로 바꾸고, 진입 시 **주(Week)별 S2 요약을 카드 하나씩** 보여주기.

**BE**: `GET /s2` 이미 구현됨. 변경 없음.

---

## 1. API 계약 (참고)

- **GET /s2**  
  - Query: `week_start` (optional, YYYY-MM-DD), `limit` (default 10, max 50)  
  - 응답: `{ "summaries": [ { "id", "tldr", "bullets", "extra": { "week_start", "topic_name" }, "created_at" } ] }`  
  - 인증: `Authorization: Bearer <Firebase ID token>` (기존과 동일)

---

## 2. Android 작업 목록

### 2.1 네비게이션 라벨 변경

| 파일 | 작업 |
|------|------|
| `ui/navigation/Destination.kt` | `Map`의 `label`을 `"Map"` → `"Weekly Summary"`로 변경. `route`는 그대로 `"map"` 유지해도 됨 (기존 딥링크/이미 쓴 경로 유지). |
| (선택) | 아이콘을 `Icons.Filled.Map` 대신 `Icons.Filled.Summarize` 등으로 바꿀 수 있음. |

### 2.2 S2 API 클라이언트

| 파일 | 작업 |
|------|------|
| **신규** `data/remote/S2Api.kt` | Retrofit 인터페이스: `GET("s2")` + `@Query("week_start") weekStart: String?`, `@Query("limit") limit: Int`. 응답용 data class: `S2Response(summaries: List<S2SummaryItem>)`, `S2SummaryItem(id, tldr, bullets, extra: S2Extra?, created_at)`, `S2Extra(week_start: String?, topic_name: String?)`. |
| `data/remote/ApiClient.kt` | `val s2Api: S2Api = retrofit.create(S2Api::class.java)` 추가. |

### 2.3 S2 리포지토리

| 파일 | 작업 |
|------|------|
| **신규** `data/repository/S2Repository.kt` | `getS2Summaries(weekStart: String? = null, limit: Int = 20)` 구현. `ApiClient.s2Api` 호출 후 성공 시 `Result.Success(summaries)`, 실패 시 `Result.Error(message)` 반환. (기존 `DocumentsRepository` 패턴 참고.) |

### 2.4 Weekly Summary 화면 (기존 Map 자리)

| 파일 | 작업 |
|------|------|
| `ui/screens/map/MapScreen.kt` **수정** 또는 **신규** `ui/screens/weekly/WeeklySummaryScreen.kt` | **진입 시**: `S2Repository.getS2Summaries()` 호출 (week_start 없이, limit 20 등). **UI**: 주별로 카드 하나 — 리스트 항목 = `summaries`의 각 요소. **카드 내용**: 해당 주 라벨(예: `extra.week_start` → "Week of 2025-02-24" 또는 "이번 주" 포맷), `tldr`, `bullets`(처음 3~5개만 표시하거나 접기/펼치기). **상태**: 로딩 중, 빈 목록(아직 S2 없음), 에러(재시도 버튼). (선택) Pull-to-refresh. |
| `ui/navigation/AppNavHost.kt` | `Destination.Map.route`일 때 기존 `MapScreen()` 대신 위에서 만든 **Weekly Summary 화면**을 보여주도록 연결. (파일명을 `WeeklySummaryScreen.kt`로 했다면 `WeeklySummaryScreen()` 호출.) |

### 2.5 카드 컴포넌트

| 파일 | 작업 |
|------|------|
| **신규** `ui/components/WeeklySummaryCard.kt` | 한 주 S2용 카드: `week_start`/날짜 라벨, `tldr`, `bullets`(처음 3개 + "N more"). **Open** 버튼 → 상세 화면으로 이동. **Re-process** 버튼 → 해당 주 S2 재생성(POST /jobs/s2 + trigger worker 후 새로고침). |

### 2.6 로컬 캐시 + 상세 화면

| 파일 | 작업 |
|------|------|
| **신규** `data/repository/S2Cache.kt` | S1/Documents와 동일 패턴: SharedPreferences에 `List<S2SummaryItem>` JSON 저장. `getCachedSummaries`, `saveCachedSummaries`. |
| **WeeklySummaryScreen** | 진입 시 캐시 있으면 먼저 표시, 병행으로 `GET /s2` 호출 후 결과로 갱신하고 캐시에 저장. Pull-to-refresh 시에도 API 호출 후 캐시 저장. |
| **신규** `ui/screens/map/WeeklySummaryDetailScreen.kt` | Open 시 전체 카드 보기(Feed 상세처럼): 주 라벨, tldr 전체, bullets 전체. TopAppBar + Back. |
| **Destination + AppNavHost** | `S2Detail` 라우트 `s2_detail/{id}` 추가. Map 탭에서 Open → `S2Detail.createRoute(id)` 로 이동. |

---

## 3. 작업 순서 제안

1. **Destination.kt** — 라벨 "Map" → "Weekly Summary", 아이콘 `Summarize`, `S2Detail` 라우트 추가  
2. **S2Api.kt** — GET /s2, POST /jobs/s2 + 응답 data class  
3. **ApiClient.kt** — `s2Api` 등록  
4. **S2Cache.kt** — 캐시 저장/로드  
5. **S2Repository.kt** — `getS2Summaries`, `enqueueS2Job`  
6. **WeeklySummaryCard.kt** — 카드 + Open / Re-process 버튼  
7. **WeeklySummaryScreen.kt** — 캐시 우선 로드, 리스트, Pull-to-refresh, Re-process 시 enqueue + trigger + 새로고침  
8. **WeeklySummaryDetailScreen.kt** — Open 시 전체 요약 표시  
9. **AppNavHost.kt** — Map → WeeklySummaryScreen, S2Detail → WeeklySummaryDetailScreen  

---

## 4. 체크리스트

- [x] 하단 네비에 "Weekly Summary" 표시
- [x] 탭 진입 시 `GET /s2` 호출 (Bearer 토큰)
- [x] 응답의 각 주(week)당 카드 1개 표시
- [x] 카드에 주 라벨(week_start 기준) + tldr + bullets 노출
- [x] 로딩/빈 목록/에러 처리
- [x] Pull-to-refresh
- [x] **로컬 캐시**: 한 번 불러오면 캐시에 저장, 다음 진입 시 캐시 먼저 표시 후 API로 갱신
- [x] **Re-process**: 카드별 Re-process 버튼 → 해당 주 `week_start`로 POST /jobs/s2 + trigger worker → 새로고침
- [x] **Open**: 카드에서 Open → 상세 화면에서 전체 tldr + bullets 표시 (S1 카드 Open과 동일한 UX)
