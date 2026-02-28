# Learning Agent — Usage Flow 제안

현재 구조를 기준으로, 사용자가 **문서 추가 → RAG 질의**까지 자연스럽게 이어지도록 하는 흐름 개선 제안입니다.

---

## 1. 현재 플로우 요약

| 단계 | 화면 | 상태 |
|------|------|------|
| 로그인 | SignIn | ✅ |
| 문서 목록 | Feed | ✅ URL ingest, 목록, 선택 칩, 삭제, Process |
| 문서 상세 | FeedDetail | ✅ 요약(tldr, bullets)만 표시 |
| RAG 질의 | Ask | ✅ 선택된 문서 또는 전체 문서로 질의 |
| 노트 | Notes | ⚠️ Fake 데이터, Add Note TODO |
| 지도 | Map | ⚠️ placeholder (example.com WebView) |
| 추천 | Recommendations | ⚠️ Fake 데이터, 액션 TODO |

**선택(selection) 흐름:** Feed에서 카드 탭 → "RAG will use: …" 칩 표시 → Ask 탭으로 이동해 질의.  
선택은 **Feed에서만** 가능하고, Ask 탭에서는 “Clear selection”만 가능.

---

## 2. 제안 요약 (우선순위)

### 🔴 High — RAG까지 이어지는 핵심 경로

1. **Ask 탭에서 문서 선택 가능하게**
   - 현재: 문서 선택은 Feed에서만 가능 → Ask에 와서는 “선택 안 됨” 또는 “Clear”만 가능.
   - 제안: Ask 화면 상단 배너에 **“문서 선택”** 버튼 추가 → 바텀시트나 다이얼로그로 **최근 문서 목록**을 보여주고, 여기서 선택하면 `selectedDocumentId` 갱신.
   - 효과: “먼저 질문 생각났다” → Ask로 와서 그다음 문서 고르는 흐름 지원.

2. **FeedDetail에서 “이 문서로 질문하기”**
   - 현재: 상세(요약/불릿)만 보고 Back → Feed로 돌아가서 카드 선택 → Ask 이동.
   - 제안: FeedDetail 상단/하단에 **“Ask about this”** (또는 “이 문서로 질문”) 버튼 추가.  
     클릭 시 `selectedDocumentId`/`selectedDocumentTitle` 설정 후 **Ask 탭으로 네비게이트** (또는 Ask 화면으로 이동하면서 해당 문서가 선택된 상태).
   - 효과: 문서 읽고 → 바로 “이걸로 질문하고 싶다” 액션 한 번에 처리.

3. **첫 사용 시 짧은 가이드(선택)**
   - 예: 문서가 0개일 때 Feed에 “URL을 입력해 문서를 추가한 뒤, 카드를 눌러 선택하고 Ask 탭에서 질문해 보세요” 한 줄 문구.
   - 또는 첫 로그인 시 한 번만 표시되는 작은 툴팁: “문서를 선택하면 Ask 탭에서 그 문서만 대상으로 답변합니다.”

---

### 🟡 Medium — 일관성 & 다음 기능

4. **Feed 카드 액션 의미 명확히**
   - 현재: **Open** = 상세, 카드 탭 = 선택(토글). “RAG will use” 칩이 선택 상태를 나타냄.
   - 제안:  
     - 카드에 **“Use for Ask”** / “선택” 같은 라벨을 작게 넣거나,  
     - Open과 **“Ask about this”**를 카드 메뉴/버튼으로 분리해서 “보기”와 “질문에 사용”을 구분.
   - 효과: 새 사용자가 “선택이 뭔지”, “Open이랑 뭐가 다른지” 덜 헷갈림.

5. **Notes ↔ 문서 연결**
   - 현재: Notes는 FakeRepository, DocumentCard의 “Add Note”는 TODO.
   - 제안 (단계적):  
     - 1단계: “Add Note”를 누르면 해당 문서 제목/URL을 포함한 노트 작성 바텀시트 열기 (문서 컨텍스트만 넘김).  
     - 2단계: 백엔드 notes API 연동 후, 문서별 노트 목록/필터.
   - 효과: “이 문서 보면서 메모” 플로우가 한 앱 안에서 완결.

6. **삭제 후 선택 정리**
   - 이미 구현됨: `onDocumentDeleted`에서 삭제한 문서가 선택 중이면 선택 해제.  
   - 추가 고려: 삭제 성공 스낵바에 “선택이 해제되었습니다”를 넣거나, 선택 해제만 조용히 유지 (현재처럼) 중 하나로 통일.

---

### 🟢 Lower — 탭 정리 & 확장

7. **Map / Recommendations**
   - 현재: Map은 example.com WebView, Recommendations는 Fake 데이터.
   - 제안:  
     - **단기:** 탭 라벨에 “(Coming soon)” 또는 비활성화된 탭으로 두고, 클릭 시 “준비 중” 토스트/스낵바.  
     - **중기:** 백엔드/기획이 있으면 지도는 실제 지식 그래프 URL, 추천은 API 연동 후 실제 추천 리스트로 교체.

8. **온보딩(선택)**
   - 첫 실행 시 2~3장 슬라이드: “문서 추가 → (선택) → Ask에서 질문” 요약.  
   - Skip 가능, “다시 보지 않기” 저장.

---

## 3. 구현 시 팀에서 정할 것

- **선택 상태 공유:**  
  `selectedDocumentId` / `selectedDocumentTitle`가 이미 MainActivity에서 유지되므로,  
  Ask에서 “문서 선택” UI만 추가하고 같은 state를 갱신하면 됨.  
  FeedDetail → Ask 이동 시에는 `navController`로 Ask route로 이동 + 동일 state 설정.
- **문서 목록 API:**  
  Ask에서 선택 다이얼로그용 목록은 기존 `GET /documents` (예: limit=20, include_summary=false) 재사용 가능.
- **우선순위:**  
  위에서 🔴 1, 2번만 먼저 하면 “문서 고르기 → 질문하기” 경로가 크게 개선됨.  
  그다음 Notes 연동(5), 카드 라벨(4), Map/Recommendations 정리(7) 순으로 적용하면 됨.

---

## 4. 플로우 다이어그램 (목표)

```
[Sign In] → [Feed]
              ├─ URL 입력 → Ingest → (Process) → 문서 카드
              ├─ 카드 탭 → "RAG will use: …" (선택)
              ├─ Open → [FeedDetail] → "Ask about this" → [Ask] (해당 문서 선택)
              ├─ Delete → 확인 → 삭제 & 선택 해제
              └─ (선택) Add Note → [Notes 연동 시 문서 컨텍스트]

[Ask]
  ├─ (선택 없음) "No document selected — answers will use all your documents"
  ├─ "문서 선택" → 최근 문서 목록에서 선택 → 배너에 "Asking about: …"
  ├─ 질문 입력 → Ask → 답변 표시
  └─ "Clear selection" → 전체 문서로 질의

[Notes]  → (현재 Fake) → 추후 문서별 노트 / Add Note with document context
[Map]    → (현재 placeholder) → Coming soon 또는 실제 지식 그래프
[Recommendations] → (현재 Fake) → Coming soon 또는 API 연동
```

이 문서는 팀에서 usage flow 논의할 때 기준으로 쓰시면 됩니다. 필요하면 특정 항목만 골라서 이슈/태스크로 쪼개도 좋습니다.
