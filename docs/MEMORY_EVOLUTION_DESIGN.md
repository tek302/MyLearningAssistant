# Memory Evolution Design — Deep Dive

**목적:** 이 프로젝트의 핵심 가치인 "Advising Professor처럼 작동하는 추천"의 구체적 메커니즘을 설계한다.  
**범위:** 2-Stage Recommendation Pipeline, keyword-anchored profile, keyword expansion, quality evaluation.  
**성격:** 논문을 읽고 실험하면서 점진적으로 채워나가는 living document.  
**선행 문서:** `PERSONALIZED_MEMORY_ARCHITECTURE_DRAFT.md` (전체 구조), `RESEARCH_KEYWORD_TREE_AND_ROADMAP.md` (논문 목록), `PERSONALIZED_MEMORY_EXECUTION_PLAN.md` (구현 계획)

---

## 0. Core Architectural Vision: 2-Stage Recommendation Pipeline

### 핵심 철학

이 프로젝트의 가치는 **"Advising Professor"처럼 작동하는 추천**에 있다.

좋은 지도교수는:
1. 학생의 관심사와 읽은 논문을 **파악하고 있고**
2. "이 키워드도 한번 봐봐"라고 **새로운 연구 방향을 제안**하고
3. 학생이 동의하면 그 방향의 **구체적 논문을 추천**해준다

단순히 "니가 읽은 것과 비슷한 논문"이 아니라, **"니가 아직 모르지만 알아야 할 것"**을 찾아주는 것이 핵심 가치.

### 2-Stage Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│  Stage 1: Keyword Recommendation (방향 제안)                  │
│                                                             │
│  입력:  explicit keywords + S2 consolidation + feedback      │
│  처리:  파생/관련/emerging keyword 탐색                       │
│  출력:  새 keyword 후보 N개 제안                              │
│  사용자: Accept ✓ / Reject ✗                                 │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  Stage 2: Paper Recommendation (논문 추천)                    │
│                                                             │
│  입력:  original keywords + accepted new keywords            │
│  처리:  arXiv 검색 + embedding similarity + scoring           │
│  출력:  추천 논문 리스트                                       │
│  사용자: Thumbs up/down                                      │
└─────────────────────────────────────────────────────────────┘
```

### Stage 1이 제안하는 keyword의 3가지 유형

| 유형 | 설명 | 예시 (사용자 keyword: "RAG") |
|------|------|----------------------------|
| **하위/인접 개념** | 기존 keyword의 세분화 또는 관련 기법 | "query decomposition", "hybrid retrieval" |
| **논문에서 반복 등장하지만 keyword에 없는 것** | S2/S1에서 자주 나오는데 사용자가 아직 keyword로 등록하지 않은 개념 | "chunk reranking", "citation grounding" |
| **관련 분야의 emerging 개념** | 최근 arXiv에서 급증하는 관련 키워드 | "graph RAG", "agentic retrieval" |

### 이 구조의 설계 원칙

> **Trackable:** 모든 추천에는 "어떤 keyword 때문에 이 논문이 추천되었는가"가 추적 가능하다.  
> **Explainable:** 사용자가 추천 근거를 keyword 수준에서 이해할 수 있다.  
> **Controllable:** 사용자가 keyword를 추가/삭제/수정하면 추천이 즉시 반영된다.

---

## 1. Core Problem Statement

> 현재 시스템은 콘텐츠를 요약하고(S1/S2), 추천하고(arXiv recommendation), 질문에 답한다(RAG).  
> 하지만 **추천이 왜 이루어졌는지 설명할 수 없고**, 사용자의 관심사 변화가 추천에 체계적으로 반영되지 않는다.

2-Stage Pipeline 도입 전후 비교:

| 현재 | 목표 |
|------|------|
| S2 text + notes + feedback → embedding similarity → 논문 추천 | **사용자 keywords → keyword expansion → accept/reject → 확장된 keywords로 논문 추천** |
| 추천 근거가 embedding 내부에 숨어있음 | 추천 근거가 keyword로 명시적 |
| 사용자 피드백이 다음 추천에 약하게 반영 | accept/reject가 profile을 직접 변경 |
| interest drift 감지 메커니즘 없음 | keyword 추가/삭제가 drift의 explicit signal |
| profile이라는 개념 자체가 없음 | **profile = accepted keyword set + weights** |

---

## 2. Design Decisions Map — Simplified

### Complexity Reduction Audit

2-Stage Pipeline과 keyword-anchored 접근을 도입하면서, 기존 D1-D7 중 상당수가 **자동으로 해결되거나 병합된다.**

| 기존 Decision | 기존 문제 | 2-Stage Pipeline에서의 상태 | 이유 |
|:---:|-----------|:---:|------|
| D1 | Profile build algorithm | **흡수 → 신규 D1** | Profile = accepted keyword set. 복잡한 algorithm 불필요 |
| D2 | Interest drift detection | **흡수 → 신규 D1** | keyword accept/reject가 drift의 explicit signal. 별도 감지 불필요 |
| D3 | Memory decay strategy | **축소 → 신규 D3** | keyword weight의 time decay만 남음 |
| D4 | Consolidation trigger | **축소 → 신규 D4** | Stage 1 실행 시점 = consolidation. S2와 동기화 |
| D5 | Profile representation | **흡수 → 신규 D1** | keyword list + metadata가 profile. 별도 설계 불필요 |
| D6 | Profile quality evaluation | **축소 → 신규 D5** | keyword accept rate + paper feedback rate로 단순화 |
| D7 | Episodic → Semantic boundary | **제거** | keyword가 semantic anchor. raw signals는 weight 계산에만 사용. 별도 경계 불필요 |
| D8 | Keyword expansion algorithm | **신규 D2 (핵심)** | Stage 1의 핵심. 이 프로젝트의 가장 어려운 문제 |
| D9 | Keyword granularity control | **흡수 → 신규 D2** | keyword expansion의 하위 문제 |
| D10 | Stage 1 ↔ Stage 2 timing | **흡수 → 신규 D4** | 운영 결정 |

### 새로운 Design Decisions (5개)

| # | Design Decision | 핵심 질문 | 난이도 | 섹션 |
|---|----------------|----------|:------:|------|
| D1 | Keyword-Anchored Profile | profile = keyword set. 어떤 metadata를 keyword에 붙이는가? | 낮음 | §3 |
| **D2** | **Keyword Expansion Algorithm** | **Stage 1에서 어떻게 좋은 파생 keyword를 제안하는가?** | **높음 — 핵심** | §4 |
| D3 | Keyword Weight & Decay | keyword weight를 어떻게 계산하고 시간에 따라 감쇠하는가? | 중간 | §5 |
| D4 | Pipeline Timing & Trigger | Stage 1/2가 언제 실행되는가? | 낮음 | §6 |
| D5 | Quality Evaluation | 추천 품질을 어떻게 측정하는가? | 중간 | §7 |

> **핵심 인사이트:** 기존 10개 design decision 중 진짜 어려운 것은 **D2 (Keyword Expansion Algorithm) 하나**다.  
> 나머지는 keyword-anchored 접근에 의해 자연스럽게 답이 나온다.

---

## 3. D1: Keyword-Anchored Profile

### 문제

사용자의 "관심사"를 어떻게 표현하는가?

### 결정: Profile = Accepted Keyword Set + Metadata

기존 D1(profile build algorithm), D2(drift detection), D5(profile representation), D7(episodic→semantic boundary)이 모두 이 하나로 수렴한다.

```jsonc
{
  "keywords": [
    {
      "keyword": "personalized RAG",
      "weight": 0.85,
      "source": "user_explicit",     // user_explicit | stage1_accepted | s2_derived
      "added_at": "2026-02-15",
      "last_activity": "2026-03-10",
      "accept_count": 3,             // Stage 1에서 이 keyword 관련 제안을 accept한 횟수
      "paper_feedback": {
        "thumbs_up": 5,
        "thumbs_down": 1
      },
      "status": "active"             // active | declining | archived
    }
  ]
}
```

### 왜 이것으로 충분한가

| 기존 설계의 고민 | Keyword-Anchored에서의 답 |
|----------------|------------------------|
| Topic taxonomy를 어떻게 정의? | **사용자가 keyword로 직접 정의.** Folksonomy 원리 (LACE, SIGIR 2023) |
| Topic normalization? | **사용자가 관리.** "RAG"와 "retrieval augmented generation"이 같은지는 사용자가 결정 |
| Interest drift 감지? | **keyword 추가 = emerging, 삭제 = declining, weight 감소 = fading.** Explicit signal |
| Profile 형태? | **keyword list + metadata.** 별도의 narrative summary나 embedding 불필요 (v1) |
| Episodic → Semantic 경계? | **keyword가 semantic anchor.** Raw signals (notes, feedback, S2)는 keyword weight 계산에만 사용 |

### Keyword의 4가지 Source

| Source | 설명 | 예시 |
|--------|------|------|
| `user_explicit` | 사용자가 직접 등록 | 앱에서 "keyword 추가" |
| `stage1_accepted` | Stage 1 keyword suggestion을 accept | "graph RAG" 제안 → ✓ Accept |
| `stage1_rejected` | Stage 1 suggestion을 reject (negative signal로 보관) | "quantum computing" 제안 → ✗ Reject |
| `s2_derived` | S2에서 반복 등장하지만 아직 keyword가 아닌 것 (Stage 1의 후보 pool) | S2에 3주 연속 "prompt engineering" 등장 |

### Interest Drift = Keyword 변화 이력

별도의 drift detection algorithm이 필요 없다. Keyword의 lifecycle 자체가 drift다:

```
Week 1:  keywords = [RAG, agent memory]
Week 3:  Stage 1 suggests "graph RAG" → user accepts
         keywords = [RAG, agent memory, graph RAG]
Week 5:  Stage 1 suggests "quantum ML" → user rejects
         reject_log += ["quantum ML"]
Week 8:  "RAG" keyword의 weight가 decay로 0.3 이하 → status: declining
Week 10: 사용자가 "RAG" 삭제 → status: archived
```

이 이력이 곧 interest drift의 완전한 log이며, 100% trackable하고 explainable하다.

### 관련 논문

| 논문 | 핵심 적용 |
|------|---------|
| **LACE** (SIGIR 2023) | Editable concept profile. 사용자가 concept 추가/삭제/rename → 추천 즉시 반영. **우리의 keyword accept/reject와 동일한 패턴** |
| **O-Mem** (2025) | Persona Memory의 Add/Ignore/Update operation. Keyword-anchored profile의 operation model과 대응 |
| **Folksonomy temporal profiling** (2008-2014) | 사용자가 직접 부여한 tag의 시간적 변화를 tracking. Tag = keyword |
| **Spotify Taste Profile** (2026) | 산업계 구현: 사용자가 직접 profile을 편집하여 추천 제어 |

---

## 4. D2: Keyword Expansion Algorithm ⭐ 핵심

### 문제

Stage 1의 핵심: **사용자의 기존 keyword + 최근 활동으로부터 "좋은" 파생 keyword를 어떻게 찾는가?**

이것이 이 프로젝트에서 **가장 어렵고 가장 가치 있는 문제**다.

### 입력

| 입력 | 내용 |
|------|------|
| `active_keywords` | 사용자의 현재 keyword set (with weights) |
| `s2_recent` | 최근 2-4주의 S2 consolidated summaries |
| `feedback_history` | 논문 추천에 대한 thumbs up/down + 해당 논문의 keywords |
| `reject_log` | 이전에 reject된 keyword 제안들 (30일 이내 재제안 방지, 이후 재제안 가능) |

### Option A: LLM-Based Expansion

```
주어진 정보:
- 사용자 keywords (with weights): {active_keywords}
- 최근 읽은 논문 요약: {s2_recent}
- 좋아한 논문의 키워드들: {positive_feedback_keywords}
- 이전에 거절한 키워드들 (30일 이내 재제안 불가): {reject_log_recent}

정확히 3개의 새로운 research keyword를 제안해주세요.
각 유형에서 1개씩:
1. 기존 keyword의 하위/인접 개념 → parent_keyword 명시
2. 최근 읽은 논문에서 반복 등장하지만 아직 keyword에 없는 개념 → 가장 관련 높은 기존 keyword를 parent로
3. 관련 분야에서 최근 부상하고 있는 개념 → parent_keyword: null (독립적)

각 keyword에 대해 JSON 출력:
- keyword: string
- type: "하위/인접" | "반복등장" | "emerging"
- parent_keyword: string | null (hierarchical 관계)
- reason: string (제안 이유, 1문장)
- confidence: float (0.0-1.0)
```

**장점:** 풍부한 추론, 관계 파악, 자연어 설명  
**단점:** LLM의 knowledge cutoff, hallucination 가능 (존재하지 않는 연구 방향 제안), 재현성 없음  
**비용:** ~$0.01-0.03/call (gpt-4o-mini)

### Option B: arXiv Co-occurrence Mining

**메커니즘:**
- 사용자 keywords로 arXiv 검색 → 최근 N개 논문 수집
- 그 논문들에서 자주 등장하지만 사용자 keyword에 없는 term 추출
- TF-IDF 또는 KeyBERT로 candidate keyword ranking

**장점:** 실제 arXiv 데이터 기반 — hallucination 없음, "emerging" 판단이 실제 논문 빈도 기반  
**단점:** keyword extraction 품질에 의존, semantic 관계 파악 약함, 구현 복잡도 높음

### Option C: Hybrid (B → A)

**메커니즘:**
1. arXiv co-occurrence로 candidate keyword pool 생성 (grounding)
2. LLM이 pool에서 선별 + 설명 생성 (reasoning)

**장점:** grounding + reasoning의 결합. Hallucination 방지 + 풍부한 설명  
**단점:** 2단계 파이프라인

### ✅ 결정 (확정, 2026-03-14)

> **Option A (LLM-Based Expansion)으로 v1 진행.** 이유:
> 1. 구현이 가장 빠르다 — prompt 하나로 시작 가능
> 2. 사용자의 accept/reject feedback이 LLM 제안의 품질을 빠르게 검증해준다
> 3. Hallucination은 사용자의 reject로 필터링된다 (human-in-the-loop)
> 4. Accept rate가 낮으면 Option C로 전환하여 grounding 추가
>
> **v2 전환 기준:** accept rate < 50%이면 Option C (Hybrid)로 전환

### 확정된 운영 정책

| 항목 | 결정 | 근거 |
|------|------|------|
| **주당 제안 수** | **3개** | 사용자 부담을 최소화. 유형별 1개씩 (하위/인접, 반복등장, emerging) |
| **Reject 재제안** | **1개월 후 재제안 가능** | 관심이 돌아올 수 있음. reject_log에 rejected_at 기록 → 30일 경과 시 재제안 pool에 복귀 |
| **Hierarchical 관계** | **포함** | 제안 시 parent keyword를 명시. e.g., "graph RAG" (parent: RAG). 사용자가 keyword 간 관계를 파악할 수 있도록 |

### Keyword suggestion 출력 형식 (v1)

```jsonc
{
  "suggestions": [
    {
      "keyword": "graph RAG",
      "type": "하위/인접",         // 하위/인접 | 반복등장 | emerging
      "parent_keyword": "RAG",    // hierarchical 관계
      "reason": "최근 S2에서 graph structure 기반 retrieval 논문 2건 등장",
      "confidence": 0.8
    },
    {
      "keyword": "chunk reranking",
      "type": "반복등장",
      "parent_keyword": "personalized RAG",
      "reason": "최근 3주 S2에서 reranking 관련 내용이 반복적으로 언급됨",
      "confidence": 0.7
    },
    {
      "keyword": "test-time compute",
      "type": "emerging",
      "parent_keyword": null,      // 기존 keyword와 직접 관계 없는 emerging topic
      "reason": "2026년 AI 분야 전반에서 급부상 중인 연구 방향",
      "confidence": 0.6
    }
  ]
}
```

### Keyword History 기능

사용자가 **explicit keyword + suggested & accepted keyword의 전체 이력**을 조회할 수 있어야 한다.

| 기능 | 설명 |
|------|------|
| **Keyword Timeline** | 각 keyword가 언제 추가/accept/reject/archived 되었는지 시간순 표시 |
| **Source 표시** | keyword별로 user_explicit / stage1_accepted / stage1_rejected 구분 |
| **Hierarchical View** | parent-child 관계를 트리 형태로 시각화 |
| **Accept/Reject 히스토리** | Stage 1에서 제안된 모든 keyword와 사용자 응답 기록 |
| **Weight 추이** | 각 keyword의 weight 변화를 주간 단위로 표시 |

이 기능은 추천의 trackability를 사용자에게 직접 보여주는 핵심 UI이다.

```
예시 화면:

📋 My Keywords
─────────────────────────────────────────
🟢 personalized RAG    w:0.85  ★ explicit   since W1
  └─ chunk reranking   w:0.72  ✓ accepted   since W5 (parent: personalized RAG)
🟢 agent memory        w:0.80  ★ explicit   since W1
  └─ graph RAG         w:0.65  ✓ accepted   since W3 (parent: RAG)
🟡 RAG                 w:0.35  ★ explicit   since W1  ⚠ declining
🔴 GPU optimization    w:0.15  ★ explicit   since W1  → archived W8

📊 Stage 1 History
─────────────────────────────────────────
W8: test-time compute (emerging) → ✗ rejected
W7: chunk reranking (반복등장) → ✓ accepted
W6: quantum ML (emerging) → ✗ rejected
W5: graph RAG (하위/인접) → ✓ accepted
```

### 남은 열린 질문

- [ ] "Emerging" 판단을 LLM의 general knowledge에 의존해도 되는가? arXiv 실시간 데이터가 필요한가?
- [ ] Parent-child 관계가 2단계 이상 깊어질 수 있는가? (grandchild keyword)

### 관련 논문

| 논문 | 핵심 적용 |
|------|---------|
| **Scholar Inbox** (ACL 2025) | Active learning으로 사용자 rating 수집 → 추천 학습. 800K+ rating dataset 공개 |
| **LOOM** (2025) | LLM 대화에서 학습 needs 추론 → thematic category로 태깅 → 학습 자료 생성. **우리 Stage 1과 가장 유사한 도메인** |
| **K-LaMP** (ACM Web 2024) | Entity-centric knowledge store. 사용자 활동에서 entity 추출 → 공개 knowledge graph에 projection |
| **LACE** (SIGIR 2023) | Retrieval-enhanced concept bottleneck. Global concept inventory에서 사용자에게 맞는 concept 검색 |

---

## 5. D3: Keyword Weight & Decay

### 문제

각 keyword의 "중요도"를 어떻게 계산하고, 시간이 지남에 따라 어떻게 감쇠하는가?

### ✅ 확정된 Decay 정책

| 항목 | 결정 | 근거 |
|------|------|------|
| **τ, β parameter** | **사용자 공통** (τ=60, β=1.5 default) | v1에서는 단순하게 시작. 데이터 축적 후 개인화 검토 |
| **`user_explicit` keyword** | **decay 미적용** | 사용자가 직접 등록한 keyword는 사용자가 직접 삭제하기 전까지 유지 |
| **Weight threshold** | **threshold 이하 시 사용자에게 확인** | weight < 0.3이면 "이 keyword 아직 관심 있어?" 알림. 사용자가 응답 없으면 30일 후 자동 archived |

### 설계

```python
def compute_keyword_weight(kw, signals, now):
    if kw.source == "user_explicit":
        base = 1.0
        decay = 1.0  # explicit keyword는 decay 미적용
    else:
        base = 0.7
        age_days = (now - kw.last_activity).days
        decay = exp(-(age_days / tau) ** beta)  # tau=60, beta=1.5

    # Feedback reinforcement
    fb = kw.paper_feedback
    feedback_score = (fb.thumbs_up - fb.thumbs_down) / max(fb.thumbs_up + fb.thumbs_down, 1)

    # S2 frequency (최근 4주 S2에서 등장 횟수)
    s2_freq = count_in_recent_s2(kw.keyword, weeks=4) / 4.0

    weight = base * (1 + feedback_score + s2_freq) * decay

    # Threshold check (stage1_accepted only)
    if kw.source != "user_explicit" and weight < 0.3:
        trigger_interest_check(kw)  # "이 keyword 아직 관심 있어?"

    return weight
```

### 핵심 원칙

| 원칙 | 구현 |
|------|------|
| `user_explicit` keyword는 사용자가 관리 | decay 미적용. 사용자가 삭제해야만 제거 |
| `stage1_accepted` keyword는 자연 감쇠 | FuXi-γ식 exponential-power decay 적용 |
| Positive feedback = reinforcement | thumbs_up이 많으면 weight 증가 |
| Weight < 0.3 → 사용자에게 확인 | "아직 관심 있어?" 알림 → 응답 없으면 30일 후 archived |
| 사용자가 삭제하면 즉시 제거 | status → archived, weight → 0 |

### 관련 논문

| 논문 | 연도 | 핵심 메커니즘 | 우리 구현 적용 |
|------|:----:|------------|-------------|
| **FuXi-γ** | 2025 | Exponential-Power Temporal Encoder: `exp(-(Δt/τ)^β)`. Ebbinghaus forgetting curve 기반 tunable decay. 4개 데이터셋 SOTA | **v1 decay function 직접 차용** (τ=60, β=1.5) |
| **FuXi-Linear** | 2026 | FuXi-γ 후속. Linear attention + Temporal Retention Channel로 장기 시퀀스 확장 | v2에서 per-user adaptive τ, β 고려 시 참고 |
| **Personalized Interest-Forgetting Markov Model** | AAAI 2015 | 사용자마다 forgetting speed, initial interest, relearning rate가 다름을 모델링. 개인화 forgetting | v2에서 per-user parameter 도입 시 핵심 참고. v1은 사용자 공통 파라미터 |
| **TD-DNN** | 2022 | Exponential time decay를 DNN에 통합한 추천 시스템. Deep learning + temporal decay 결합 | Time decay가 추천 품질에 유의미한 영향을 준다는 실증 근거 |
| **STIM** | 2025 | Forgetting curve + spatio-temporal periodic interest. Meituan 수억 DAU 실 서비스 적용, 거래량 1.54% ↑ | 대규모 서비스에서 forgetting curve 효과 입증. Periodic pattern 참고 |
| **MemoryBank** | AAAI 2024 | Ebbinghaus forgetting curve + positive feedback reinforce | Decay + feedback reinforcement 조합의 근거 |
| **Memoria** | 2024 | KG triplet + exponential decay `w = e^(-a·x)` 실증 | Exponential decay 효과 실증 |

#### 논문 링크

- FuXi-γ: [arxiv.org/abs/2512.12740](https://arxiv.org/abs/2512.12740)
- FuXi-Linear: [arxiv.org/abs/2602.23671](https://arxiv.org/abs/2602.23671)
- Personalized Interest-Forgetting Markov Model: [cdn.aaai.org/ojs/9165](https://cdn.aaai.org/ojs/9165/9165-13-12693-1-2-20201228.pdf)
- TD-DNN: [mdpi.com/2076-3417/12/13/6398](https://www.mdpi.com/2076-3417/12/13/6398)
- STIM: [arxiv.org/html/2508.02451](https://arxiv.org/html/2508.02451v1)

#### v1 → v2 전환 시 논문 참고 매핑

| v1 구현 | v2 확장 가능성 | 참고 논문 |
|---------|--------------|----------|
| τ=60, β=1.5 고정 | per-user adaptive τ, β | AAAI 2015 (Personalized Forgetting), FuXi-Linear |
| 사용자 공통 파라미터 | 사용 패턴 기반 자동 조절 | TD-DNN (학습 기반 접근) |
| `user_explicit` no-decay | 유지 (설계 의도) | — |
| Declining threshold 0.3 | 데이터 기반 calibration | STIM (실 서비스 데이터 검증) |

### 남은 열린 질문

- [ ] Threshold 0.3은 적절한가? 실제 데이터로 calibration 필요
- [ ] "아직 관심 있어?" 알림에 "Yes"로 응답하면 weight를 얼마나 복구하는가? (0.5로 reset? 현재값 유지?)

---

## 6. D4: Pipeline Timing & Trigger

### 문제

Stage 1과 Stage 2가 언제 실행되는가?

### 설계

```
매주 S2 consolidation 완료
  └→ Stage 1 실행 (keyword expansion suggestion 생성)
       └→ 사용자에게 push notification: "이번 주 keyword 제안이 있습니다"
            └→ 사용자가 accept/reject 완료
                 └→ Stage 2 실행 (확장된 keyword로 논문 추천)
```

### 결정

> **Weekly batch, S2와 동기화.** 이유:
> 1. S2가 "이번 주 무엇을 읽었는가"의 요약이므로, keyword expansion의 자연스러운 trigger
> 2. 사용자에게 주 1회 "keyword 리뷰 + 논문 추천" 루틴 제공
> 3. Stage 1 → 사용자 응답 → Stage 2 사이의 시간차는 허용 (비동기)

### Keyword 수동 추가/삭제는 즉시 반영

- 사용자가 keyword를 추가/삭제하면 profile은 즉시 업데이트
- 하지만 Stage 2 (논문 추천)은 다음 주기까지 대기 (또는 on-demand trigger 제공)

---

## 7. D5: Quality Evaluation

### 문제

추천 품질을 어떻게 측정하는가?

### 2-Stage 구조의 장점: 평가가 단순해진다

| 측정 지점 | 지표 | 의미 |
|----------|------|------|
| **Stage 1 quality** | `keyword_accept_rate` = accepted / suggested | Keyword 제안이 사용자 관심에 부합하는 비율 |
| **Stage 2 quality** | `paper_feedback_rate` = thumbs_up / total_recommended | 추천 논문이 실제로 유용한 비율 |
| **전체 pipeline** | `accept_rate × feedback_rate` | End-to-end 추천 품질 |
| **Drift tracking** | 주간 keyword set 변화량 | 관심사가 얼마나 진화하고 있는가 |
| **Retention** | 사용자가 주간 keyword review를 지속하는가 | 시스템이 가치를 제공하고 있는가 |

### 기존 D6(Profile Quality Eval)이 불필요해진 이유

기존에는 "profile이 사용자의 관심사를 얼마나 잘 반영하는가?"를 별도로 평가해야 했다. 하지만 keyword-anchored 접근에서는 **profile = 사용자가 직접 승인한 keyword set**이므로, profile의 정확도는 정의상 100%다 (사용자가 accept한 것이 profile이니까).

평가해야 할 것은 **profile 자체가 아니라 Stage 1의 suggestion 품질**이며, 이것은 `keyword_accept_rate`로 직접 측정된다.

### 관련 논문

- **RLPA** (NeurIPS 2025): "profile quality를 reward로 측정"하는 접근 → 우리는 accept_rate가 reward 역할
- **Prottasha et al.** (2025): Profile updating benchmark dataset → 우리 profile update 패턴 비교에 활용 가능

---

## 8. Complexity Reduction Summary

기존 7+3 = 10개 Design Decision이 **5개로 축소**되었다.

```
기존 (10개)                          신규 (5개)
─────────────────────────           ─────────────────────
D1  Profile build algorithm    ──┐
D2  Interest drift detection   ──┼──→  D1  Keyword-Anchored Profile
D5  Profile representation     ──┤
D7  Episodic → Semantic boundary ┘
D3  Memory decay strategy      ────→  D3  Keyword Weight & Decay
D4  Consolidation trigger      ──┬──→  D4  Pipeline Timing & Trigger
D10 Stage timing               ──┘
D6  Profile quality evaluation ────→  D5  Quality Evaluation
D8  Keyword expansion algorithm ─┬──→  D2  Keyword Expansion Algorithm ⭐
D9  Keyword granularity control ─┘
```

### 왜 줄어들었는가

**핵심 원리: "사용자에게 결정을 돌려주면, 시스템이 결정할 필요가 없다"**

| 시스템이 결정해야 했던 것 | 이제 사용자가 결정하는 것 |
|------------------------|----------------------|
| 어떤 topic이 "관심사"인가? (D1) | 사용자가 keyword를 등록/accept한다 |
| 관심사가 변했는가? (D2) | 사용자가 keyword를 추가/삭제한다 |
| Profile을 어떤 형태로 저장? (D5) | keyword list + metadata면 충분 |
| Episodic → Semantic 경계? (D7) | keyword가 semantic anchor. 구분 불필요 |
| Profile 품질 평가? (D6) | accept_rate로 직접 측정 |

남은 진짜 어려운 문제는 **D2 (Keyword Expansion Algorithm)** — 이것은 사용자에게 돌릴 수 없다. 시스템이 좋은 키워드를 제안하는 능력 자체가 핵심 가치.

### Trackability & Explainability 달성

모든 추천의 trace가 명확하다:

```
"이 논문이 추천된 이유"
  → 이 논문은 keyword "graph RAG" 관련입니다
    → keyword "graph RAG"는 Week 5에 Stage 1이 제안하고 사용자가 Accept했습니다
      → 제안 이유: "기존 keyword 'RAG'의 최근 발전 방향"
        → 기반 데이터: S2 Week 4에서 graph structure 관련 논문 3건 읽음
```

---

## 9. Experiment Plan

2-Stage Pipeline 검증을 위한 실험 계획. 기존 실험을 새 구조에 맞게 수정.

### Experiment 1: Keyword Expansion Prompt v0

**목적:** D2의 Option A (LLM-Based Expansion)이 실제로 유용한 keyword를 제안하는지 확인

**방법:**
1. 현재 DB에서 실제 keywords, S2, feedback export
2. Stage 1 prompt 작성 → LLM에게 keyword suggestion 요청
3. 생성된 keyword 후보를 수동으로 accept/reject 판단
4. Accept rate 측정

**판단 기준:**
- Accept rate > 50%이면 Option A로 v1 진행
- Accept rate < 30%이면 Option C (Hybrid)로 전환 검토
- 제안된 keyword의 유형 분포 (하위/인접 vs 반복등장 vs emerging)

**상태:** ☐ Not started

### Experiment 2: End-to-End Pipeline Dry Run

**목적:** 2-Stage Pipeline의 전체 흐름을 수동으로 실행하여 UX 확인

**방법:**
1. Experiment 1에서 accept한 keyword로 arXiv 검색
2. 기존 keyword-only 추천 vs 확장된 keyword 추천 비교
3. 추가된 keyword가 실제로 더 좋은 논문을 가져오는지 확인

**판단 기준:**
- 확장 keyword로 발견된 논문 중 "이건 내가 직접 찾지 못했을 것"이 있는가?
- Keyword expansion 없는 추천과 비교해서 유의미한 차이가 있는가?

**상태:** ☐ Not started

### Experiment 3: Keyword Weight Decay 관찰

**목적:** D3의 decay function이 합리적으로 작동하는지 확인

**방법:**
1. 실제 4-8주 사용 데이터에 decay function 적용
2. Declining으로 분류된 keyword가 실제로 관심이 줄어든 것인지 확인

**상태:** ☐ Not started (Experiment 1, 2 이후)

---

## 10. Decision Log

| 날짜 | Decision | 선택 | 근거 |
|------|----------|------|------|
| 2026-03-14 | 전체 구조 | **2-Stage Recommendation Pipeline** 채택 | 추천의 trackability/explainability 확보. "Advising Professor" UX. D1-D10 → D1-D5 단순화 |
| 2026-03-14 | D1 | **Keyword-Anchored Profile** | 기존 D1/D2/D5/D7을 통합. 사용자의 explicit keyword가 profile의 anchor |
| 2026-03-21 | D2 | **Option A (LLM-Based Expansion) 확정** | 구현 속도 우선. Human-in-the-loop으로 hallucination 필터링. Accept rate < 50% 시 Option C 전환 |
| 2026-03-21 | D2 운영 | **주 3개 제안, reject 1개월 후 재제안, hierarchical 관계 포함** | 사용자 부담 최소화. 관심 복귀 허용. Keyword 간 관계 파악 |
| 2026-03-21 | D2 기능 | **Keyword History UI** | explicit + suggested + accepted 전체 이력 조회. Trackability의 사용자 대면 기능 |
| 2026-03-21 | D3 | **explicit keyword decay 면제, stage1_accepted만 decay 적용** | 사용자가 직접 등록한 것은 사용자가 직접 관리 |
| 2026-03-21 | D3 parameter | **τ, β는 사용자 공통** (τ=60, β=1.5) | v1 단순화. 데이터 축적 후 개인화 검토 |
| 2026-03-21 | D3 threshold | **weight < 0.3 → "아직 관심 있어?" 확인** | 자동 제거 대신 사용자 확인. 30일 무응답 시 archived |
| 2026-03-14 | D4 | **Weekly batch, S2 동기화** | 자연스러운 trigger. 주 1회 루틴 |
| 2026-03-14 | D3 참고문헌 | **Weight Decay 논문 7편 정리** | FuXi-γ/Linear, AAAI 2015 Personalized Forgetting, TD-DNN, STIM, MemoryBank, Memoria. v1→v2 전환 매핑 포함 |

---

## Appendix A: Literature Review Archive

기존 논문 리뷰는 새로운 D1-D5 구조에서도 유효한 참고자료로 보존한다.

### A.1 Profile Build 관련 논문 (기존 D1 연구)

| 논문 | 연도 | 핵심 메커니즘 | 우리 적용 | 읽음? |
|------|:----:|------------|---------|:-----:|
| PersonaRAG | 2025 | 5개 agent LLM prompting, 세션 내 실시간 personalization | 장기 profile과는 다른 맥락 | ☑ |
| Enabling Personalized Long-term Interactions (Westhäußer) | 2025 | Predefined JSON → LLM incremental update | Structured JSON 구조 참고. LLM-only 효과 미입증 결과 중요 | ☑ |
| A-MEM | 2025 | Memory evolution (Zettelkasten). Ablation: evolution 제거 시 성능 하락 | "기존 profile을 update하는 것"의 중요성 입증 | ☑ |
| Memoria | 2024 | KG triplet + exponential decay | Decay function 실증: `w = e^(-a·x)` | ☑ |
| O-Mem | 2025 | Active profiling, Add/Ignore/Update, NN clustering, IDF scoring | Keyword operation model의 근거 (SOTA) | ☑ |
| Prottasha et al. | 2025 | LLM profile construction/updating. Open dataset | Profile updating benchmark | ☑ |
| RLPA | 2025 | RL로 profile 추론 학습. Profile quality = reward | D5 evaluation 참고 | ☑ |
| MIND | 2019 | Multi-interest extraction (capsule network) | 사용자는 multi-interest → keyword list로 표현 | ☑ |
| Al Alshaikh | 2020 | 연구 논문 추천에서 동적 multi-concept profile | 도메인이 가장 가까움 | ☑ |

### A.2 Interest Drift & Decay 관련 논문 (기존 D2/D3 연구)

| 논문 | 연도 | 핵심 메커니즘 | 우리 적용 | 읽음? |
|------|:----:|------------|---------|:-----:|
| IDURL | 2025 | Interest Drift Quantization — category 분포 변화로 drift 정량화 | 주간 keyword set 변화량 측정의 이론적 근거 | ☑ |
| MemoryBank | 2024 | Ebbinghaus Forgetting Curve + selective forget/reinforce | D3 decay + feedback reinforcement | ☑ |
| FuXi-γ | 2025 | `exp(-(Δt/τ)^β)` tunable decay | D3 decay function 직접 적용 | ☑ |
| **FuXi-Linear** | **2026** | FuXi-γ 후속. Linear attention + Temporal Retention Channel | v2 long-sequence 참고 | ☐ |
| STIM | 2025 | Forgetting curve + periodic pattern. Meituan 수억 DAU 적용 | "매주 반복 등장 = stable" 패턴. 실 서비스 검증 | ☑ |
| **Personalized Interest-Forgetting Markov** | **AAAI 2015** | 사용자별 forgetting speed/initial interest/relearning rate 개인화 | v2 per-user τ, β 도입 시 핵심 근거 | ☐ |
| **TD-DNN** | **2022** | Exponential time decay + DNN 결합 추천 시스템 | Time decay가 추천 품질에 유의미한 효과 실증 | ☐ |
| Modhi et al. | 2019 | Component-based preference — 각 component가 다른 속도로 변화 | stable vs volatile keyword 분리 근거 | ☑ |

### A.3 Keyword-Anchored & Explicit Profile 관련 논문 (신규 조사)

| 논문 | 연도 | 핵심 메커니즘 | 우리 적용 | 읽음? |
|------|:----:|------------|---------|:-----:|
| LACE — Editable User Profiles | 2023 | Concept-value bottleneck. 사용자가 concept 편집 → 추천 즉시 반영 | **D1의 이론적 근거.** Keyword = concept | ☑ |
| Scholar Inbox | 2025 | Active learning, 사용자 explicit rating. 800K rating dataset | D5 evaluation + Stage 2 참고 | ☑ |
| LOOM — Dynamic Learner Memory Graph | 2025 | LLM 대화에서 학습 needs 추론 → thematic tag → learning material 생성 | **Stage 1과 가장 유사한 구조** | ☑ |
| K-LaMP | 2024 | Entity-centric knowledge store from user activity → KG projection | Keyword를 entity로, S2를 activity로 대응 | ☑ |
| Folksonomy temporal profiling (Yin et al.) | 2012 | User-tag-specific temporal model. Topic switch 감지 | Tag = keyword. Tag 빈도 × time decay | ☑ |
| Time Forgetting in Topic-Based User Interest Profiling | 2013 | Tag 기반 topic profiling + time forgetting function | D3의 직접 근거 | ☑ |
| BONSAI | 2025 | 사용자가 자연어로 feed intent 정의. Include/exclude 제어 | 사용자의 explicit control이 추천 품질 향상에 기여하는 증거 | ☑ |

### A.4 미읽은 논문 (향후 참고)

| 논문 | 관련 Decision | 우선순위 |
|------|:------------:|:-------:|
| A Survey of Personalization: From RAG to Agent | D2 전반 | P2 |
| Position: Episodic Memory is the Missing Piece | 참고 | P3 |
| Synapse: Episodic-Semantic Memory via Spreading Activation | 참고 | P3 |
| LaMP benchmark | D5 | P2 |
| PersonaBench | D5 | P2 |
| HyperBandit: Contextual Bandit for Time-Varying Preferences | D3 | P3 |
| COPR: Continual Human Preference Learning | D3 | P3 |
| **FuXi-Linear** (2026) — [arxiv.org/abs/2602.23671](https://arxiv.org/abs/2602.23671) | D3 | **P2** |
| **Personalized Interest-Forgetting Markov** (AAAI 2015) — [cdn.aaai.org/ojs/9165](https://cdn.aaai.org/ojs/9165/9165-13-12693-1-2-20201228.pdf) | D3 | **P2** |
| **TD-DNN** (2022) — [mdpi.com/2076-3417/12/13/6398](https://www.mdpi.com/2076-3417/12/13/6398) | D3 | P3 |
| **Adaptive Forgetting Curves for Spaced Repetition** — [core.ac.uk/works/85611470](https://core.ac.uk/works/85611470/) | D3 참고 | P3 |

---

## 참고 문서

- `PERSONALIZED_MEMORY_ARCHITECTURE_DRAFT.md` — 전체 6-layer 구조, layer별 현재/목표 비교
- `PERSONALIZED_MEMORY_EXECUTION_PLAN.md` — DB schema, API, job flow 구현 계획
- `RESEARCH_KEYWORD_TREE_AND_ROADMAP.md` — 논문 목록, 6주 research roadmap
- `EVALUATION_BENCHMARKS_AND_STRATEGY.md` — 평가 벤치마크, LLM-as-judge 전략
- `POST_MVP_BACKLOG.md` — 구현 backlog

---

*문서 작성: 2026-03-14. 최종 수정: 2026-03-14. 2-Stage Pipeline 중심으로 전면 재편.*  
*D3 Weight Decay 관련 논문 7편 정리 및 v1→v2 전환 매핑 추가.*  
*핵심 미해결 문제: D2 (Keyword Expansion Algorithm). Experiment 1로 검증 시작 필요.*
