# Evaluation Benchmarks & Strategy

**목적:** Personalized summary와 recommendation의 품질을 정량적으로 측정하기 위한 benchmark, dataset, evaluation 방법론을 정리한다.  
**참고:** personalized memory architecture는 `PERSONALIZED_MEMORY_ARCHITECTURE_DRAFT.md`, 실행 계획은 `PERSONALIZED_MEMORY_EXECUTION_PLAN.md`, launch 전략의 핵심 가설/검증 기준은 `LAUNCH_STRATEGY_AND_REVENUE_MODEL.md` §7 참고.

---

## 1. 핵심 가설

> **"사용자가 4주 이상 사용하면, 추천 품질이 체감 가능하게 좋아지는가?"**

이 가설을 증명하기 위해 **offline evaluation (LLM-as-judge, benchmark)** 과 **online evaluation (user feedback metric)** 을 조합한다.

---

## 2. 관련 Academic Benchmark & Dataset

### 2.1 Personalized Summary 평가

#### PersonalSum (NeurIPS 2024, Datasets & Benchmarks Track)

- **내용:** 일반 독자의 요약 선호를 수집한 최초의 human-annotated personalized summarization dataset. 1,375개의 수동 annotated summary. 뉴스 기사 대상.
- **구조:** user profile + source article → personalized summary vs generic summary 비교.
- **핵심 발견:** entity/topic만으로는 다양한 사용자 선호를 설명하기 어려움. 기존 LLM의 personalized summarization 성능이 아직 부족.
- **접근:** [HuggingFace](https://huggingface.co/datasets/PersonalLab/PersonalSum), [GitHub](https://github.com/SmartmediaAI/PersonalSum)
- **이 시스템과의 연결:** S1/S2 summary가 사용자에게 맞춤화되는 방향으로 진화할 때, evaluation methodology를 참고할 수 있음. 다만 뉴스 도메인이라 연구 논문 도메인과 gap 있음.

#### 전통적 Summary 평가 Metric

| Metric | 측정 대상 | 한계 |
|--------|----------|------|
| ROUGE-1/2/L | n-gram overlap with reference | Personalization을 측정하지 못함 |
| BERTScore | Semantic similarity with reference | ROUGE보다 낫지만 여전히 reference 의존 |
| UniEval / G-Eval | LLM 기반 multi-dimensional scoring (coherence, fluency, relevance, consistency) | Personalization 차원이 없지만 summary 자체 품질 평가에 유용 |

---

### 2.2 Personalized Recommendation 평가

#### AgentRecBench (2025)

- **내용:** LLM agent 기반 personalized recommendation 시스템을 위한 benchmark. Interactive textual recommendation simulator 포함.
- **3가지 평가 시나리오:** classic recommendation, **evolving-interest** (관심사 변화), cold-start.
- **핵심:** 10가지 classical + agentic recommendation 방법 비교. Agentic system이 우수.
- **이 시스템과의 연결:** **Evolving-interest 시나리오**가 가장 relevant. 시간이 지나며 관심사가 변하는 사용자에게 추천을 맞추는 문제.

#### RecBench+ (2025)

- **내용:** LLM의 복잡한 추천 요구 처리 능력을 평가. ~30,000 query (영화/도서 도메인).
- **핵심 발견:** LLM은 명시적 조건은 잘 처리하지만, reasoning이 필요하거나 misleading한 정보가 있는 query에서 약함.
- **이 시스템과의 연결:** explicit keyword와 implicit interest를 함께 반영하는 추천에서, 어떤 유형의 query가 어려운지 참고.

#### PerRecBench (2025)

- **내용:** LLM의 personal preference 이해도를 grouped ranking으로 평가. 19개 LLM 비교.
- **핵심 발견:** 큰 모델이 일반적으로 낫지만 personalized recommendation에서 여전히 부족. Pairwise/listwise ranking이 pointwise보다 우수.
- **이 시스템과의 연결:** arXiv recommendation의 reranking 방식에 listwise ranking approach 적용 검토.

---

### 2.3 Personalized RAG / User Profile 평가

#### LaMP Benchmark (ACL 2024)

- **내용:** 7개의 personalized task (text classification + generation). Retrieval augmentation 포함. Personalized email subject generation, personalized news headline generation, **personalized citation recommendation** 등.
- **Retrieval 방법:** term matching, semantic matching, **time-aware** retrieval.
- **이 시스템과의 연결:** 가장 광범위한 personalized LLM evaluation framework. Personalized RAG v1 구현 시 evaluation methodology 참고에 적합.

#### PersonaBench (2025)

- **내용:** RAG pipeline이 personal information을 얼마나 잘 이해하는지 평가. Synthetic user profile + private document에서 질문 답변.
- **핵심 발견:** 현재 retrieval-augmented model들이 이 task에서 struggle.
- **이 시스템과의 연결:** "사용자의 notes, feedback, keywords에서 정보를 검색해서 답변/추천에 반영"하는 구조와 직접 연결.

#### PersonaMem (2025)

- **내용:** LLM이 **evolving user profile**을 얼마나 잘 추적하는지 평가. 180+ simulated user profile, 60 multi-turn conversation session, 15 real-world task.
- **핵심 발견:** GPT-4.5, Gemini-2.0 같은 frontier model도 dynamic user profile tracking에서 ~50% accuracy.
- **이 시스템과의 연결:** **가장 직접적으로 relevant한 benchmark 중 하나.** S2 + feedback으로 user interest를 추적하는 것이 정확히 이 문제. "4주 후 추천이 좋아지는가?"를 측정하는 데 evaluation 방법론을 직접 차용할 수 있음.

---

### 2.4 논문/Citation Recommendation 평가

#### LitSearch (2024)

- **내용:** ML/NLP 논문에 대한 597개의 realistic literature search query. Inline citation 기반 GPT-4 생성 질문 + 저자 직접 작성 질문.
- **핵심 발견:** BM25와 dense retriever 사이에 큰 성능 gap. LLM reranking이 추가로 성능 향상.
- **이 시스템과의 연결:** arXiv recommendation에서 retrieval 품질 측정에 직접 사용 가능.

#### CiteRAG (2026)

- **내용:** Citation prediction을 위한 최초의 RAG benchmark. 554K 논문 corpus, 7,267 / 8,541 instance.
- **2가지 task:** coarse-grained (어떤 논문을 인용할까) + fine-grained (어디에서 인용할까).
- **이 시스템과의 연결:** "사용자가 관심 있을 논문을 찾는" 문제와 직접 연결.

#### MDCR (Multi-Domain Citation Recommendation)

- **내용:** 여러 과학 분야에 걸친 citation recommendation benchmark.
- **이 시스템과의 연결:** 추천 소스를 arXiv 이외로 확장할 때 참고.

---

### 2.5 LLM-as-Judge 관련 연구

- LLM judge가 human preference와 높은 일치도를 보임 (Kendall's τ = 0.87, Cranfield-style movie recommendation).
- Profile-aware LLM judge가 human judgment과 high fidelity로 match (podcast recommendation 연구).
- 단, 단순한 persona 기반 LLM-as-Personalized-Judge는 한계 있음. Verbal uncertainty estimation을 포함하면 일치도가 80% 이상으로 향상.
- Evaluation에 Gwet's AC2, rank correlation coefficients가 Krippendorff's alpha보다 robust.

---

## 3. 실용적 Evaluation 전략

### 3.1 LLM-as-Judge (Offline, 자동화 가능)

#### Summary 평가 Prompt

```
당신은 personalized summary의 품질을 평가하는 evaluator입니다.

[사용자 프로필]:
{user_interest_profile_summary}

[이번 주 S2 요약]:
{s2_summary_text}

아래 세 가지 차원에서 1-5점으로 평가하고, 각각 한 줄 근거를 제시하세요.

1. Relevance: 사용자의 관심사와 관련된 내용인가?
2. Specificity: 사용자의 구체적 관심사를 반영하는가? (generic하지 않은가?)
3. Actionability: 사용자가 다음 행동(논문 읽기, 연구 방향 조정 등)에 도움이 되는가?

JSON 형식으로 응답:
{"relevance": {"score": N, "reason": "..."}, "specificity": {"score": N, "reason": "..."}, "actionability": {"score": N, "reason": "..."}}
```

#### Recommendation 평가 Prompt

```
당신은 personalized research paper recommendation의 품질을 평가하는 evaluator입니다.

[사용자 컨텍스트]:
- 최근 읽은 문서: {recent_document_titles}
- 최근 노트: {recent_notes_text}
- 관심 키워드: {user_keywords}
- 최근 positive feedback: {positive_feedback_summary}
- 최근 negative feedback: {negative_feedback_summary}

[이번 주 추천]:
1. {rec_1_title} - {rec_1_abstract_snippet}
2. {rec_2_title} - {rec_2_abstract_snippet}
3. {rec_3_title} - {rec_3_abstract_snippet}

각 추천에 대해 아래 세 가지 차원으로 1-5점 평가하고, 한 줄 근거를 제시하세요.

1. Relevance: 사용자의 현재 관심사와 관련이 있는가?
2. Novelty: 이미 읽은 것의 반복이 아닌, 새로운 정보를 제공하는가?
3. Serendipity: 사용자가 아직 모르지만 관심 가질 만한 것인가?

JSON 형식으로 응답:
{"recommendations": [{"title": "...", "relevance": {"score": N, "reason": "..."}, "novelty": {"score": N, "reason": "..."}, "serendipity": {"score": N, "reason": "..."}}, ...]}
```

#### A/B 비교 Prompt

```
당신은 두 개의 추천 세트를 비교하는 evaluator입니다.

[사용자 컨텍스트]:
{user_context}

[Set A - Baseline (profile 미반영)]:
1. {a_1_title}
2. {a_2_title}
3. {a_3_title}

[Set B - Personalized (profile 반영)]:
1. {b_1_title}
2. {b_2_title}
3. {b_3_title}

어느 세트가 이 사용자에게 더 적합한가? A 또는 B를 선택하고, 이유를 설명하세요.
또한, 각 세트의 overall quality를 1-10으로 평가하세요.

JSON 형식으로 응답:
{"preferred": "A" or "B", "reason": "...", "score_a": N, "score_b": N}
```

### 3.2 User Feedback 기반 Online Metric

| Metric | 계산 | 의미 |
|--------|------|------|
| **Precision@K** | thumbs_up / (thumbs_up + thumbs_down) per week | 추천이 맞는가 |
| **Precision Trend** | Week 1 Precision vs Week 4 Precision | 핵심 가설: 시간이 지나면 좋아지는가 |
| **Process Rate** | 추천 중 process(ingest)한 비율 | 실제 행동으로 이어지는가 |
| **Remove Rate** | 추천 중 remove한 비율 | 역방향 signal |
| **Feedback Participation** | feedback 준 유저 / 추천 받은 유저 | 유저가 engagement하고 있는가 |
| **Interest Drift Tracking** | Week N과 Week N+4의 추천 topic 변화 vs 실제 ingest topic 변화 | 시스템이 관심사 변화를 따라가는가 |

### 3.3 A/B Comparison (Profile 유무 비교)

가장 간단하면서 강력한 offline evaluation:

- Condition A: profile/feedback 없이 S2 topic만으로 추천 (baseline)
- Condition B: profile + feedback + notes 반영한 추천 (personalized)
- 동일 사용자, 동일 주차에 대해 두 버전의 추천을 생성하고:
  - LLM-as-judge로 A vs B 비교
  - 또는 사용자에게 두 세트를 보여주고 선호 수집 (alpha 유저 대상)

---

## 4. 단계별 Evaluation 전략

| 단계 | 방법 | 난이도 | 시점 |
|------|------|--------|------|
| **지금** | LLM-as-judge로 S2 summary + recommendation quality scoring 자동화 | 낮음 | 바로 가능 |
| **Alpha** | User feedback 기반 online metric 수집 (Precision@3, Process Rate) | 낮음 | alpha 시작 시 |
| **Alpha 중** | Precision Trend (Week 1 vs Week 4) 측정 — 핵심 가설 검증 | 중간 | 4주 이후 |
| **Profile layer 구현 후** | A/B comparison (baseline vs personalized) | 중간 | profile layer 이후 |
| **고도화** | PersonaMem, LaMP 등 학술 benchmark로 formal evaluation | 높음 | research 진행 시 |

---

## 5. 구현 계획

LLM-as-judge evaluation pipeline의 구체적 구현 계획은 `PERSONALIZED_MEMORY_EXECUTION_PLAN.md` §10 참고.

---

*문서 작성: 2026-03 기준. 학술 benchmark 정보는 작성 시점 공개 자료·논문 검색 결과 기준이며, 일부 최신 논문은 preprint(arXiv) 기준이다.*
