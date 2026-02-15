# 🧠 Agentic Learning & Research App (Android + Backend)

## 1️⃣ 목표 정의
- 사용자가 지정한 토픽(예: “Mobile GPU”, “LLM Serving”, “미국 국채”)에 대해 **소스 수집 → 요약 → 정리 → 알림**
- 사용자의 **메모·하이라이트**와 함께 영구 보관
- 주기적 **학습 플랜/퀴즈 생성**, **주간/월간 브리핑** 자동 발행
- 후속 **리서치 액션** 유도 (코드, 논문, 데이터셋 등)

---

## 2️⃣ 시스템 아키텍처
```
Android (Jetpack Compose)
  ├─ Auth (Google Sign-In)
  ├─ Topic 관리, 피드/요약/퀴즈 보기
  ├─ 푸시노티 (FCM)
  └─ API 클라이언트 (Retrofit + OkHttp)

Backend (FastAPI or NodeJS)
  ├─ Gateway/API Layer
  ├─ Orchestrator (LangGraph/LangChain)
  ├─ Data Layer (Postgres + pgvector / Firestore)
  ├─ Retrieval (RAG + 랭킹)
  ├─ Observability
  └─ Security

Jobs & Pipelines (Event-driven)
  ├─ 주기 수집(Cron) & 실시간 Webhook
  ├─ 요약/브리핑/퀴즈 생성
  └─ 사용자 맞춤 푸시/이메일 송신
```
---

## 3️⃣ 핵심 기능 모듈
1. **소스 연결:** RSS/YouTube/X, PDF 업로드 등  
2. **전처리/임베딩:** 텍스트 추출, 번역, chunking  
3. **요약·큐레이션·퀴즈:** TL;DR, Key Points, MCQ 생성  
4. **피드백 루프:** 👍👎, 태그, 메모  
5. **알림:** 신규 토픽, 중요 업데이트

---

## 4️⃣ DB 모델 (요약)
`users`, `topics`, `sources`, `chunks`, `embeddings`, `notes` 등으로 구성  
→ `pgvector`를 통한 벡터 검색 및 개인화 추천

---

## 5️⃣ 주요 API 예시
- `/v1/topics` — 토픽 CRUD  
- `/v1/ingest/url` — URL/문서 인제스트  
- `/v1/feeds` — 요약 피드  
- `/v1/notes` — 메모·하이라이트 저장  
- `/v1/quiz/generate` — 학습 퀴즈 생성  
- `/v1/briefings` — 주간/월간 브리핑  

---

## 6️⃣ 에이전트 오케스트레이션
LangGraph 기반 명시적 상태 머신  
```
UserEvent → [TopicResolver] → [Fetcher] → [Normalizer]
         → [Deduper] → [Embedder] → [RAG Summarizer]
         → [Curator] → [Notifier]
```

---

## 7️⃣ Android 앱
- **UI:** Jetpack Compose + Material 3  
- **상태:** MVVM + Kotlin Coroutines + Flow  
- **네트워킹:** Retrofit/OkHttp  
- **로컬 저장:** Room + DataStore  
- **기능:** 로그인 → 피드 → 메모 → 학습  
- **WorkManager:** 주기적 동기화, FCM 알림  

---

## 8️⃣ MVP 로드맵 (12주)
| 단계 | 목표 | 주요 기능 |
|------|------|------------|
| W1–2 | MVP 1 | 기본 API, Android 토픽 피드 |
| W3–4 | MVP 2 | 요약/푸시 알림 |
| W5–6 | MVP 3 | YouTube 자막, 브리핑 |
| W7–8 | MVP 4 | 퀴즈/학습 플랜 |
| W9–12 | 확장 | 고급 커넥터, 공유공간 |

---

## 9️⃣ 품질·운영
- **지표:** Summarization faithfulness, latency, cost, retention  
- **관측:** OpenTelemetry + Prometheus  
- **보안:** OAuth2, PII 마스킹, Audit 로그  

---

## 🔟 비용 가이드
- LLM 요약/임베딩: 월 수~수십 달러  
- GCP Cloud Run + Cloud SQL: 월 30~60달러 수준  

---

## 11️⃣ 추가 기능 제안

### (1) 업로드 문서 기반 집중 학습
- **기능:** PDF/URL 업로드 → 하이라이트 지정 → 선택 영역에 대해 **Focus-RAG** 기반 심층 학습  
- **자동 생성:** 요약, 핵심 개념 카드, 선수지식, 오해 포인트, 예제, 퀴즈, 후속 추천  
- **데이터 모델:** `focus_anchors`, `concepts`, `concept_mentions`, `learnpacks`  

### (2) 개인 지식 DB + Mind Map 시각화
- **개념 그래프:** Concept 노드 + Relation 엣지 + Evidence 링크  
- **저장소:** Postgres + pgvector → (확장 시) Neo4j  
- **웹 시각화:** Next.js + Cytoscape.js  
  - 필터, Focus+Context, Diff 뷰, Export, 공유 링크  
- **Android 연계:** “내 학습” 탭에 개념 카드/미니뷰, 웹 딥링크 지원  

### (3) 지능형 학습 어시스턴트 확장
- 문맥 기반 질문 응답 (문서 + 개념 기반 Q&A)  
- 학습 이력 추적 및 개인화 곡선 모델링  
- 학습 경로 추천 (난이도, 관심도 기반)  
- 리서치 파트너 모드 (논문/코드/데이터셋 큐레이션)  

---

## 12️⃣ 실행 로드맵 (2–3 스프린트)
| 스프린트 | 목표 | 주요 결과물 |
|-----------|------|--------------|
| Sprint 1 | 업로드/하이라이트 → Focus-RAG 요약 + LearnPack | FastAPI 스켈레톤 |
| Sprint 2 | Mind Map MVP, 퀴즈/학습 플랜 | Next.js + Cytoscape |
| Sprint 3 | 개념 병합 워크플로우, 근거 패널, Diff 뷰 | Graph UI |

---

## 🔐 보안
- 개인 스토리지(KMS 암호화)  
- 캐시 비활성화 옵션  
- 공유 시 근거 블라인드 모드  

---

## ✅ 다음 단계 제안
1. **GCP + FastAPI + pgvector** 기반 확정  
2. GitHub Repo 분리 (`android-app`, `server`)  
3. MVP 스프린트 착수 및 CI/CD 구성  

---

### 실행 옵션
- [ ] DB 스키마 & 마이그레이션 파일  
- [ ] Focus-RAG FastAPI 엔드포인트 스켈레톤  
- [ ] Next.js + Cytoscape Mind Map MVP  
- [ ] Android Compose 업로드→학습요청 플로우
