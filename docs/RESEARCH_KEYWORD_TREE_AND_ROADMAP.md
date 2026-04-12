# Research Keyword Tree And Roadmap

**목적:** Learning Assistant를 단순 문서 Q&A/RAG 앱이 아니라, `weekly summary + notes + explicit keyword + feedback`를 축적하며 시간이 지날수록 더 개인화되는 학습/추천 서비스로 고도화하기 위한 research 방향을 정리한다.  
**핵심 관점:** 중심축은 `GraphRAG` 그 자체보다 **`personalized RAG + long-term memory + user modeling + preference-aware recommendation`** 이다. Knowledge graph와 GraphRAG는 이후 구조화·고도화 레이어로 검토하는 것이 더 적절하다.

---

## 1. Research Question

> **How can a personal AI learning assistant build and use long-term user memory from weekly summaries, notes, keywords, and feedback to improve personalized retrieval and recommendation over time?**

이 질문은 현재 프로젝트 구조와 잘 맞는다.

- `S1 / raw note / events`는 **episodic memory**
- `S2 / stabilized interests / long-term topics`는 **semantic memory**
- `keyword / like-dislike / process-remove / feedback`는 **control signal + preference signal**
- recommendation은 단순 similarity가 아니라 **preference-aware retrieval + ranking** 문제로 본다

---

## 2. Keyword Tree

## 2.1 Core Layer — Personalized Memory + User Modeling

현재 서비스의 가장 중요한 연구 축이다.  
핵심 질문은 “어떤 문서를 찾을까?”보다 **“이 사용자가 지금 무엇에 관심이 있나?”** 에 가깝다.

### A. Personalized RAG

**의미**

- 사용자 프로필, notes, weekly summary, explicit keyword를 retrieval/generation에 반영
- 같은 질문이라도 사용자마다 retrieval 결과와 답변이 달라져야 함

**대표 논문**

1. **PersonaRAG: Enhancing Retrieval-Augmented Generation Systems with User-Centric Agents** (2024)
   - 사용자 중심 agent를 넣어 retrieval과 generation을 개인화하는 대표적 Personalized RAG 논문.
2. **PrLM: Learning Explicit Reasoning for Personalized RAG via Contrastive Reward Optimization** (2025, preprint)
   - retrieval된 user profile 위에서 명시적 reasoning을 학습시키는 방향.

**왜 중요한가**

- 현재 프로젝트에서 `summary + note + keyword + feedback`를 실제로 answer/recommendation에 반영하려면 가장 먼저 필요한 축이다.

### B. User Modeling for LLM Agents

**의미**

- 사용자의 관심사, 목표, 선호, 최근 변화까지 장기 프로필로 다루는 연구 축
- recommendation과 answer의 공통 상위 레이어

**대표 논문**

1. **Enabling Personalized Long-term Interactions in LLM-based Agents through Persistent Memory and User Profiles** (2025, preprint)
   - persistent memory와 user profile을 결합해 장기 상호작용을 다루는 직접적인 논문.
2. **A Survey of Personalization: From RAG to Agent** (2025, survey)
   - Personalized RAG부터 agent personalization까지 넓게 정리한 survey.

**왜 중요한가**

- 이 축이 정리되어야 “keyword는 어디에 반영할지, notes는 어떤 profile field로 들어갈지, weekly summary는 profile인지 memory인지”를 명확히 할 수 있다.

---

## 2.2 Memory Layer — Long-Term / Episodic / Semantic Memory

현재의 `S1 -> S2 -> notes -> feedback` 구조와 가장 직접적으로 연결되는 축이다.

### A. Long-Term Memory for LLM Agents

**의미**

- 사용자의 장기 관심사와 반복 패턴을 저장·갱신하는 memory system
- 주간 summary가 누적될수록 user profile과 recommendation이 진화하는 구조

**대표 논문**

1. **A-MEM: Agentic Memory for LLM Agents** (2025)
   - memory 저장/회수/업데이트를 agentic하게 다루는 방향.
2. **Memoria: A Scalable Agentic Memory Framework for Personalized Conversational AI** (2025, preprint)
   - session-level summary와 knowledge graph형 user modeling을 결합한 프레임워크.

**왜 중요한가**

- 지금 서비스가 지향하는 “몇 주, 몇 달 지나며 더 똑똑해지는 assistant”의 기반이다.

### B. Episodic-Semantic Memory

**의미**

- raw note, interaction, clicked item, recent ingest는 episodic
- consolidated weekly summary, persistent interest, long-term topic은 semantic
- 현재 아키텍처를 memory theory로 재해석하는 핵심 틀

**대표 논문**

1. **Position: Episodic Memory is the Missing Piece for Long-Term LLM Agents** (2025)
   - episodic memory를 장기 agent의 필수 요소로 본 포지션 페이퍼.
2. **Synapse: Empowering LLM Agents with Episodic-Semantic Memory via Spreading Activation** (2025/2026 preprint 계열)
   - episodic/semantic memory를 graph 기반 activation으로 연결.

**왜 중요한가**

- S1/S2를 단순 요약 기능이 아니라 memory hierarchy로 재정의할 수 있게 해 준다.

---

## 2.3 Retrieval Layer — Profile-Conditioned Retrieval

RAG 품질보다 더 중요한 것은 **“사용자 맞춤 retrieval”** 이다.

### A. Personalized Query Expansion

**의미**

- query 자체를 user profile에 맞게 확장하거나 rewrite
- 예: 같은 `agent memory`라도 어떤 유저는 research, 어떤 유저는 product/design 관점일 수 있음

**대표 논문**

1. **Personalize Before Retrieve: LLM-based Personalized Query Expansion for User-Centric Retrieval** (2025)
   - user history를 retrieval 전단의 query expansion에 반영하는 최신 방향.
2. **Query Expansion with Enriched User Profiles for Personalized Search Utilizing Folksonomy Data** (2017)
   - 고전 personalized query expansion 계열의 대표 사례.

**왜 중요한가**

- 현재 서비스의 `keyword + recent S2 + note signal`을 retrieval 전에 반영하는 실험과 직접 연결된다.

### B. Preference-Aware Retrieval

**의미**

- retriever/reranker가 단순 semantic similarity가 아니라 user preference를 고려해야 함
- explicit keyword, weekly summary, notes, likes/dislikes를 retrieval prior로 활용

**대표 논문**

1. **Retrieval Augmented Generation with Collaborative Filtering for Personalized Text Generation** (2025)
   - user preference와 collaborative signal을 RAG에 붙이는 방향.
2. **Personalized Graph-Based Retrieval for Large Language Models** (2025)
   - graph 기반 personalization retrieval을 다룬 논문.

**왜 중요한가**

- recommendation뿐 아니라 answer quality도 “내 관심사에 얼마나 align되느냐”로 바뀌기 때문이다.

---

## 2.4 Recommendation Layer — Retrieval-Augmented Recommendation

현재 weekly recommendation을 더 발전시키는 데 가장 직접적으로 필요한 연구 축이다.

### A. Retrieval-Augmented Recommendation

**의미**

- candidate retrieval 후 LLM 또는 ranker가 reasoning과 reranking을 수행
- recommendation을 단순 vector similarity가 아니라 retrieval + reasoning으로 본다

**대표 논문**

1. **ARAG: Agentic Retrieval Augmented Generation for Personalized Recommendation** (2025)
   - user understanding, retrieval, NLI, ranking을 agentic pipeline으로 묶은 접근.
2. **RALLRec: Improving Retrieval Augmented Large Language Model Recommendation with Representation Learning** (2025)
   - retrieval-augmented recommendation 성능 향상에 초점을 둔 논문.

**왜 중요한가**

- 현재 arXiv top-3 추천을 `topic top-3`에서 `user-interest-aware ranking`으로 발전시키는 데 바로 쓸 수 있다.

### B. Preference Learning / Feedback-Driven Recommendation

**의미**

- 좋아요/싫어요, skip, process, save 같은 action을 선호 신호로 사용
- closed alpha 이후 필수적으로 중요해지는 축

**대표 논문**

1. **HyperBandit: Contextual Bandit with Hypernetwork for Time-Varying User Preferences in Streaming Recommendation** (2024)
   - 시간에 따라 변하는 user preference를 bandit 형태로 학습.
2. **COPR: Continual Human Preference Learning via Optimal Policy Regularization** (2024)
   - evolving preference를 학습하면서 catastrophic forgetting을 줄이는 관점.

**왜 중요한가**

- 현재 planned feedback system을 recommendation tuning과 직접 연결할 수 있다.

---

## 2.5 Structured Knowledge Layer — Personal Knowledge Graph / Interest Graph

이 레이어에서 `knowledge graph`가 의미를 가진다.  
다만 중심축이 아니라 **구조화 도구**로 보는 게 적절하다.

### A. Personal Knowledge Graph

**의미**

- `user / topic / keyword / paper / note / summary / feedback` 간 관계를 graph로 표현
- explainability와 multi-hop interest propagation에 강점

**대표 논문**

1. **A Personal Knowledge Graph for Recommendation** (2022)
   - 개인 데이터와 추천을 연결하는 PKG 방향의 대표 사례.
2. **Knowledge Graph Enhanced Recommender System: A Survey** (2021)
   - KG 기반 추천 전반을 정리한 survey.

**왜 중요한가**

- 지금 서비스에서 user interest를 명시적 구조로 다루고 싶다면 가장 직접적인 키워드다.

### B. User Interest Graph / Multi-Interest Modeling

**의미**

- 사용자의 관심사는 하나가 아니라 여러 개이며 시간에 따라 달라짐
- weekly summary와 notes를 interest clusters/graph로 해석할 수 있음

**대표 논문**

1. **Hierarchical Attentive Knowledge Graph Embedding for Personalized Recommendation** (2019)
   - user-item connectivities를 subgraph 기반으로 다루는 추천 논문.
2. **Knowledge-Aware User Multi-Interest Modeling Method for News Recommendation** (2024)
   - 다중 관심사를 knowledge-aware하게 모델링하는 최신 계열 논문.

**왜 중요한가**

- “요즘 이 사용자는 agent memory보다 recommendation evaluation에 더 관심이 많다” 같은 drift를 표현하기 좋다.

---

## 2.6 Advanced Layer — GraphRAG / Graph Memory Retrieval

이건 후반부 고도화 축이다.  
처음부터 메인 키워드로 둘 필요는 없고, 위 레이어들이 어느 정도 정리된 뒤 검토하는 것이 현실적이다.

### A. GraphRAG

**의미**

- 개별 chunk similarity보다 entity/relation/community 구조를 따라 retrieval
- multi-hop reasoning, topic 연결성, 설명 가능성 강화

**대표 논문**

1. **From Local to Global: A GraphRAG Approach to Query-Focused Summarization** (Microsoft, 2024)
   - Microsoft GraphRAG의 대표 논문.
2. **HippoRAG: Neurobiologically Inspired Long-Term Memory for Large Language Models** (2024)
   - graph + memory retrieval을 long-term memory 관점에서 다룬 대표 논문.

**왜 중요한가**

- topic 간 연결, related concept discovery, explanation attached recommendation 같은 고도화에 쓸 수 있다.

### B. Graph Memory for Agents

**의미**

- memory를 단순 vector store가 아니라 evolving graph로 관리
- long-term agentic memory와 가장 잘 만나는 방향

**대표 논문**

1. **REMem: Reasoning with Episodic Memory in Language Agent** (2026, preprint)
   - hybrid memory graph와 episodic reasoning을 다룸.
2. **EverMemOS: A Self-Organizing Memory Operating System for Structured Long-Horizon Reasoning** (2026, preprint)
   - 장기 메모리 운영체제 개념으로 memory lifecycle을 구조화.

**왜 중요한가**

- 단순 “지식 그래프 저장”이 아니라, 실제로 업데이트·회수·정리되는 memory substrate를 연구할 수 있다.

---

## 3. Recommended Search Keyword Bundles

아래 순서로 검색하면 지금 서비스 방향과 가장 잘 맞는 논문들을 모으기 쉽다.

1. `personalized RAG user preference modeling`
2. `long-term memory personalized LLM agent`
3. `episodic semantic memory LLM agent`
4. `personalized query expansion user profile retrieval`
5. `retrieval augmented recommendation LLM`
6. `contextual bandit recommendation user preference drift`
7. `personal knowledge graph recommendation`
8. `user interest graph multi-interest modeling`
9. `GraphRAG personalized retrieval`
10. `graph memory LLM agents`

---

## 4. Research Roadmap (6 Weeks)

## Week 1 — Problem Framing

**목표**

- 이 서비스를 `RAG app`이 아니라 **personalized learning memory + recommendation system**으로 재정의

**읽을 키워드**

- `Personalized RAG`
- `User Modeling for LLM Agents`

**읽을 논문**

- `PersonaRAG`
- `Enabling Personalized Long-term Interactions in LLM-based Agents through Persistent Memory and User Profiles`

**산출물**

- user profile schema 초안
- signal inventory 문서
- 아래 항목들의 역할 정의
  - weekly summary
  - notes
  - explicit keywords
  - feedback
  - process/remove

**핵심 질문**

- explicit signal과 implicit signal 중 무엇을 우선할까?
- user profile은 retrieval 전단, reranking, generation 중 어디에 가장 먼저 넣을까?

---

## Week 2 — Memory Architecture

**목표**

- 현재 구조를 memory architecture로 재해석

**읽을 키워드**

- `Long-Term Memory for LLM Agents`
- `Episodic-Semantic Memory`

**읽을 논문**

- `A-MEM`
- `Position: Episodic Memory is the Missing Piece for Long-Term LLM Agents`

**산출물**

- memory hierarchy 초안
- 예시 분류
  - episodic: raw note, processed recommendation, click/remove event
  - semantic: S2 summary, persistent interests, long-term topics
  - control: keywords, blocked topics, recency weights

**핵심 질문**

- S2는 semantic memory인가?
- note는 episodic인가, semantic candidate인가?
- memory decay / refresh rule이 필요한가?

---

## Week 3 — Personalized Retrieval Prototype

**목표**

- recommendation과 answer 양쪽에서 profile-conditioned retrieval 실험 시작

**읽을 키워드**

- `Personalized Query Expansion`
- `Preference-Aware Retrieval`

**읽을 논문**

- `Personalize Before Retrieve`
- `Retrieval Augmented Generation with Collaborative Filtering for Personalized Text Generation`

**실험**

- baseline: 현재 vector retrieval
- exp A: query + explicit keywords
- exp B: query + latest weekly summaries
- exp C: query + keywords + note-derived interests
- exp D: reranker에 interest profile 추가

**평가 기준**

- relevance
- novelty
- alignment with current interests
- user-specific consistency

---

## Week 4 — Recommendation Personalization

**목표**

- current topic-based recommendation을 user-interest-aware ranking으로 전환하는 설계

**읽을 키워드**

- `Retrieval-Augmented Recommendation`
- `Preference Learning / Feedback-driven Recommendation`

**읽을 논문**

- `ARAG`
- `HyperBandit`

**실험**

- 추천 점수 = relevance + novelty + recency + preference alignment
- feedback event를 반영한 weight update
- negative feedback이 retrieval scope와 rank에 미치는 영향 확인

**평가 기준**

- click/process rate
- remove rate
- explicit thumbs up/down consistency
- recommendation diversity vs precision trade-off

---

## Week 5 — Interest Graph / PKG Decision

**목표**

- graph가 실제로 필요한지 판단

**읽을 키워드**

- `Personal Knowledge Graph`
- `User Interest Graph`

**읽을 논문**

- `A Personal Knowledge Graph for Recommendation`
- `Knowledge-Aware User Multi-Interest Modeling Method for News Recommendation`

**실험**

- graph 없이 profile table/json만으로 충분한지 확인
- graph를 도입하면 어떤 relation이 필요한지 설계
  - user -> topic
  - topic -> keyword
  - keyword -> paper
  - note -> entity
  - summary -> topic
  - feedback -> interest update

**판단 기준**

- explainability 개선 여부
- multi-hop discovery 가능 여부
- recommendation 품질 상승 여부
- 유지보수 복잡도 대비 가치

---

## Week 6 — GraphRAG / Agentic Memory Retrieval

**목표**

- graph 계층이 실제 retrieval과 recommendation 품질을 올리는지 검증

**읽을 키워드**

- `GraphRAG`
- `Graph Memory for Agents`

**읽을 논문**

- `From Local to Global: A GraphRAG Approach to Query-Focused Summarization`
- `HippoRAG`

**실험**

- vector-only baseline vs graph-assisted retrieval
- user interest graph 기반 query expansion
- graph-based path explanation attached recommendation

**최종 판단**

- 품질이 확실히 오를 때만 GraphRAG 채택
- 아니면 graph는 admin/debug/explainability layer로만 유지

---

## 5. Suggested Reading Order

논문 읽기 순서는 아래가 효율적이다.

1. `PersonaRAG`
2. `Enabling Personalized Long-term Interactions in LLM-based Agents through Persistent Memory and User Profiles`
3. `A-MEM`
4. `Position: Episodic Memory is the Missing Piece for Long-Term LLM Agents`
5. `Personalize Before Retrieve`
6. `Retrieval Augmented Generation with Collaborative Filtering for Personalized Text Generation`
7. `ARAG`
8. `HyperBandit`
9. `A Personal Knowledge Graph for Recommendation`
10. `Knowledge-Aware User Multi-Interest Modeling Method for News Recommendation`
11. `From Local to Global: A GraphRAG Approach to Query-Focused Summarization`
12. `HippoRAG`

---

## 6. Final Recommendation

현재 프로젝트 기준으로는 아래 우선순위가 가장 현실적이다.

1. `Personalized RAG`
2. `Long-term memory / episodic-semantic memory`
3. `Retrieval-augmented recommendation`
4. `Personalized query expansion / preference-aware retrieval`
5. `Personal knowledge graph / interest graph`
6. `GraphRAG / graph memory`

즉, **GraphRAG는 마지막에 검토하는 고도화 옵션**으로 두고, 먼저 **personalized memory + user modeling + recommendation personalization** 을 중심으로 연구하는 것이 가장 적합하다.

---

*문서 작성: 2026-03 기준. 공개 자료·논문 검색 결과를 바탕으로 정리했으며, 일부 최신 논문은 preprint(arXiv) 기준이다.*
