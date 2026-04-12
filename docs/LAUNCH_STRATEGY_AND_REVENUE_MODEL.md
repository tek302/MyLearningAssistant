# Launch Strategy & Revenue Model

**목적:** 제품 launch 전략, 시장 포지셔닝, 수익 모델을 정리한다.  
**관점:** VC-backed startup 경로와 personal branding + indie service 경로를 나누어 검토한다.  
**참고:** 경쟁사 기능 비교는 `MARKET_COMPARISON_PM_VC.md`, alpha 우선순위는 `CLOSED_ALPHA_PRIORITY.md`, 기술 로드맵은 `RESEARCH_KEYWORD_TREE_AND_ROADMAP.md` 참고.

---

## 1. Product Positioning

### 1.1 One-liner

> **"The only learning assistant that gets smarter about YOU over time — not just answering questions, but evolving its understanding of your research interests through every document you read, every note you take, and every recommendation you engage with."**

### 1.2 핵심 차별화

시장의 유사 서비스들은 네 가지 카테고리로 나뉘며, 이 제품은 어디에도 완전히 속하지 않는 조합을 갖고 있다.

| 카테고리 | 대표 서비스 | 이들이 하지 않는 것 |
|---------|-----------|-------------------|
| **Read-it-later + Highlight** | Readwise Reader, Matter, Omnivore | 장기 topic consolidation(S2), 주간 추천, feedback-driven personalization |
| **AI Research Assistant** | Elicit, Semantic Scholar, ResearchRabbit | 장기 interest evolution tracking, episodic-semantic memory, "내 문서" 기반 RAG |
| **AI Note-taking / Second Brain** | Notion AI, Mem, Reflect, Obsidian+AI | 자동 weekly topic consolidation, 외부 논문 추천, feedback loop |
| **General AI Chat with Memory** | ChatGPT Memory, NotebookLM | 구조화된 memory hierarchy, explicit preference signal, recommendation pipeline |

**이 제품만의 조합:**

1. **End-to-end pipeline** — Ingest → S1 → RAG → S2(장기 기억) → 주간 추천이 하나의 제품에서 돌아감
2. **시간과 함께 진화하는 개인화** — S2 consolidation + feedback loop + notes 반영으로, 사용할수록 추천과 답변이 사용자에게 맞춰짐
3. **Episodic-Semantic Memory Architecture** — raw note/interaction은 episodic, consolidated summary/interest는 semantic, keyword/feedback는 control signal로 명확히 분리
4. **Data flywheel** — 사용자가 쓸수록 personalization이 올라가고 switching cost가 자연스럽게 높아지는 구조

### 1.3 Target Persona

**1차 타겟 (launch):** ML/AI 분야 PhD 학생 또는 초기 연구자 (arXiv heavy user)

- arXiv recommendation이 이미 구현되어 있음
- weekly paper reading이 habit이고, 논문 tracking pain이 명확함
- tech-savvy, early adopter 성향
- 커뮤니티가 명확 (Twitter/X ML community, r/MachineLearning, HuggingFace forums)

**2차 타겟 (확장):** 기술 분야 knowledge worker, 자기주도 학습자

- 기술 블로그, 논문, PDF 리포트를 주기적으로 읽는 사람
- 추천 소스 확장(RSS, 뉴스레터 등) 이후 가능

---

## 2. Track A — VC-Backed Startup

### 2.1 Investable Signals

| 강점 | 근거 |
|------|------|
| **Data flywheel** | 사용할수록 개인화가 올라가고 retention moat이 생기는 구조 |
| **기술적 depth** | Episodic-semantic memory, personalized RAG, feedback-driven recommendation — 최신 연구를 반영한 아키텍처 |
| **시장 timing** | AI-native productivity tool 수요 급증, 기존 read-it-later/note 도구들이 AI 전환 중 |
| **End-to-end pipeline** | S2 + 주간 추천 조합은 유사 제품에서 거의 없음 |

### 2.2 VC가 물을 질문과 리스크

| 질문 | 현실적 답변 |
|------|-----------|
| **"Why not just ChatGPT with memory?"** | ChatGPT memory는 비구조적 conversation-level. 이 시스템은 explicit signal(keywords, feedback) + implicit signal(reading pattern)을 구조적으로 결합하며, recommendation pipeline이 별도로 존재 |
| **"Android only?"** | 연구자 중 iOS/Mac 비율이 높아 TAM 제한. Web interface 또는 iOS 지원이 필수. `IOS_SUPPORT_BRAINSTORM.md` 참고 |
| **"arXiv only?"** | 추천 소스가 arXiv에 한정되면 TAM이 좁음. PubMed, SSRN, Google Scholar, general web으로의 확장이 핵심 |
| **"How do you prove recommendations get better?"** | 4주/8주/12주 사용 후 precision@3 변화, click/process rate, remove rate 추이를 보여줄 metric 필요 |
| **"경쟁사 대비 완성도?"** | MVP 단계. 상용 서비스(Readwise, Elicit, Mem)는 이미 유료 플랜, 팀 기능, 정교한 UX를 갖추고 있음 |

### 2.3 VC 경로의 필수 조건

이 경로를 택하려면 다음이 선행되어야 한다:

1. **iOS 또는 Web 지원** — Android only로는 시장 설득이 어려움
2. **추천 소스 확장** — arXiv 이외의 소스(PubMed, RSS, 뉴스레터 등)
3. **Retention metric 증명** — "4주 이상 사용하면 추천 품질이 체감 가능하게 좋아지는가?" 를 데이터로 보여야 함
4. **팀 빌딩** — Solo founder로는 투자 유치가 어려움
5. **Scalability** — multi-tenant architecture, SLA, 관측성

### 2.4 VC 경로 launch 전략

```
Month 1-2:  Closed alpha (10-30명, ML 연구자)
            → retention metric, recommendation quality 증명
Month 3-4:  Public beta
            → iOS/Web 추가, 추천 소스 확장
            → Product Hunt, HN, Twitter/X launch
Month 5-6:  Seed round pitch
            → retention data + growth rate + TAM story
```

---

## 3. Track B — Personal Branding + Indie Service

### 3.1 왜 이 경로가 현실적인가

- 만드는 과정 자체가 즐거움 — 지속 가능성의 가장 강력한 신호
- VC 경로의 리스크(팀 빌딩, 대규모 투자, 빠른 성장 압박)를 지지 않아도 됨
- "실제 서비스를 운영해본 경험" + "기술 블로그" + "오픈 포트폴리오"가 모두 확보됨
- 잘 되면 키우고, 아니어도 career asset으로 남음

### 3.2 VC 경로와 달라지는 점

| 항목 | VC 경로 | Indie / Branding 경로 |
|------|---------|----------------------|
| **Android only** | 치명적 약점 | 충분. end-to-end를 혼자 만들었다는 것 자체가 임팩트 |
| **수익 모델** | 빠른 성장, TAM 극대화 | 운영비 자급자족이면 충분 |
| **경쟁사 비교** | "Readwise보다 낫다" 증명 필요 | 불필요. 다른 지원자의 포트폴리오가 경쟁 상대 |
| **"Why not ChatGPT?"** | 방어 필요 | 오히려 "ChatGPT와 내 시스템의 차이를 분석했다"가 branding |
| **추천 소스 확장** | 필수 | 나중에 해도 됨 |
| **iOS 지원** | 필수 | optional |
| **팀** | 필요 | 불필요 |

### 3.3 이 프로젝트가 보여주는 Personal Brand Signal

현재 본업은 GPU software 개발 조직의 VP (GPU HW/SW architecture, Vulkan/OpenCL/DirectX, Triton/ROCm/CUDA, driver/compiler, SW/HW co-design, performance profiling & optimization). 이 맥락에서 이 프로젝트가 보여주는 signal은 다음과 같다. 상세 분석은 `CAREER_POSITIONING.md` 참고.

| 보이는 것 | 읽히는 signal |
|-----------|--------------|
| GPU executive가 AI application을 end-to-end로 직접 설계/구현 | "compute substrate와 application layer를 모두 이해하는 사람" |
| End-to-end solo build (Android + FastAPI + Supabase + Cloud Run) | "VP이면서도 여전히 직접 shipping할 수 있다" |
| 6주 research roadmap + 논문 reading order를 만들어 체계적으로 새 도메인 학습 | "새로운 영역을 체계적으로 학습할 수 있다" |
| Episodic-Semantic Memory Architecture 설계 | "도메인이 바뀌어도 시스템 아키텍처를 설계할 줄 안다" |
| Multi-user, auth, guardrails, admin dashboard | "production-level 사고를 한다" |
| docs 폴더의 양과 질 | "커뮤니케이션과 문서화를 잘 한다" |
| 10주+ 지속한 사이드 프로젝트 | "끈기, intellectual curiosity" |

**유의점:** "full-stack AI executive" 또는 "AI expert"로 포지셔닝하면 과장이다. GPU development와 AI application 사이의 중간 레이어(ML framework, model training, inference serving, MLOps)는 직접 경험하지 않았다. 정확한 포지셔닝은 **"AI가 실제로 어떻게 product가 되는지 직접 경험해본 GPU executive"**이다.

### 3.4 Branding 경로 launch 전략

#### Tier 1 — 반드시 해야 할 것

**Technical Blog Post Series**

일반 개발자의 "I built a cool project" 블로그가 아니라, **compute substrate를 만드는 executive가 application layer를 경험한 관점**으로 써야 한다. GPU와 AI application 사이의 bridge를 놓는 글은 당신만 쓸 수 있는 unique angle이다.

1. **"I Build GPUs for a Living. Here's What I Learned Building an AI App on Top of Them."**
   - GPU designer로서 AI application을 만들어보니 달랐던 점
   - Inference cost가 product architecture를 결정하는 방식
   - Embedding, RAG, batch processing의 실제 compute pattern
   - GPU roadmap 관점이 어떻게 바뀌었는지
   - 기반: 프로젝트 전체 경험

2. **"The Full Stack of AI Compute: What Gets Lost Between Silicon and User Experience"**
   - GPU → driver → compiler → runtime → framework → model → application의 전체 chain
   - 각 레이어의 decision이 다른 레이어에 어떻게 파급되는지
   - GPU maker와 AI app builder가 서로에 대해 모르는 것
   - 기반: 본업 경험 + 프로젝트 경험의 대비

3. **"Build to Understand: Why Executives Should Still Ship Code"**
   - VP가 왜 직접 만들어봐야 하는가
   - 새로운 도메인을 체계적으로 학습하는 approach (6주 research roadmap, 논문 reading order)
   - Intellectual curiosity가 경력의 가장 강력한 driver
   - 기반: 학습 과정 자체

**쓰지 말아야 할 주제:** "How to build a RAG system", "Deep dive into episodic-semantic memory" 같은 AI engineering tutorial. AI engineer나 연구자가 더 credible하게 쓸 수 있는 주제이며, 당신의 unique angle이 아님.

플랫폼:
- **LinkedIn article** — executive audience, recruiter 노출. 가장 높은 career ROI
- **Medium** (Towards Data Science / Towards AI publication submit) — tech community 노출
- **개인 블로그 + dev.to cross-post** — 장기 asset

**GitHub Repository 정리**

- README를 "이 프로젝트가 뭐고 왜 이렇게 만들었는지" 중심으로 재작성
- Architecture diagram (Mermaid 또는 이미지)
- 기술 선택의 이유 (why pgvector, why S1→S2, why feedback loop)
- Demo GIF 또는 짧은 video

#### Tier 2 — 하면 좋은 것

- **Twitter/X thread** — 블로그 핵심을 thread로 요약. ML community + GPU/HW community 양쪽에서 engagement 가능
- **LinkedIn post** — 블로그 게시 시마다 짧은 insight post. Executive recruiter 채널
- **Demo video (2-3분)** — ingest → 1주 후 recommendation → feedback → 다음 주 recommendation 변화 flow

#### Tier 3 — Optional

- Conference / meetup lightning talk
- GPU/AI compute conference (Hot Chips, GTC 등) 또는 AI meetup에서 cross-domain 관점 발표

---

## 4. Revenue Model — Freemium (두 경로 공통)

Freemium은 VC 경로든 indie 경로든 가장 적합한 모델이다.  
Data flywheel을 유지하려면 무료 사용자도 충분히 서비스를 써야 하고, 유료 전환은 value를 느낀 뒤에 자연스럽게 일어나야 한다.

### 4.1 운영 비용 추정

#### 고정 비용 (월)

| 항목 | Free tier 범위 | Pro 범위 (유저 50+) | 비고 |
|------|--------------|-------------------|------|
| Supabase (DB + Storage) | $0 (500MB DB) | $25/mo (8GB DB) | 유저 50+ 되면 Pro 필요 |
| Cloud Run | $0 (월 200만 req) | $5-30/mo | 소규모면 거의 무료 |
| Firebase Auth | $0 (10K MAU) | $0 | 충분 |
| Domain | — | ~$1/mo | 연 $12 정도 |
| **고정 합계** | **~$0** | **~$30-55/mo** | |

#### 변동 비용 (유저당 월)

| 작업 | 모델 | 보통 사용자 기준 |
|------|------|-----------------|
| Document ingest (embedding) | text-embedding-3-small | ~$0.01/doc × 10docs = $0.10 |
| S1 summary | gpt-4o-mini | ~$0.03/doc × 10docs = $0.30 |
| S2 weekly consolidation | gpt-4o-mini | ~$0.05 × 4weeks = $0.20 |
| Weekly recommendation | embedding + rerank | ~$0.08 × 4weeks = $0.32 |
| RAG queries | gpt-4o-mini + embedding | ~$0.03 × 20queries = $0.60 |
| **유저당 월 합계** | | **~$1.50** (heavy user: $3-5) |

### 4.2 Tier 설계

#### Free Tier — "맛보기 + data flywheel 시작"

| 제한 | 값 | 설계 이유 |
|------|---|----------|
| 월 document ingest | **5개** | 주 1-2개. 가치를 느끼기엔 충분 |
| RAG query | **월 20회** | 하루 1번 정도 |
| Weekly recommendation | **무제한** | 핵심 retention hook. 매주 돌아오게 만드는 장치 |
| S2 weekly summary | **무제한** | retention driver |
| Notes | **무제한** | cost 미미. 더 쓸수록 personalization 향상 |
| Feedback | **무제한** | data flywheel의 핵심 input |

Free tier 유저 예상 월 비용: **~$0.40-0.70** (ingest 제한 덕분에 대폭 감소)

설계 원칙: **Recommendation과 summary를 무료로 열어 "이 서비스가 나를 점점 잘 안다"를 느끼게 하고, ingest와 RAG query를 유료 전환 trigger로 사용.**

#### Pro Tier — $8/month

| 항목 | 값 |
|------|---|
| 월 document ingest | **무제한** (soft cap 100) |
| RAG query | **무제한** |
| Free 기능 전체 | 포함 |
| Priority processing | 빠른 job queue |
| Export (notes, summaries) | CSV/Markdown |
| Recommendation history | 전체 주차 열람 (Free는 최근 1주만) |
| Custom keywords | 관심 키워드 직접 설정 (user_keywords) |

가격 근거:
- $5 → "너무 싸서 가치가 없어 보임"
- $10+ → "개인 도구치고 비싸다" 심리적 저항
- $8 → Netflix basic보다 싸고, 커피 두 잔. 연구자가 수용 가능한 sweet spot
- Annual 옵션: $72/year (월 $6) → commitment + cash flow 확보

#### Team/Lab Tier — $6/seat/month (장기, VC 경로 한정)

- 5+ seats, 연간 결제
- 공유 knowledge base, team recommendation, admin dashboard
- PMF 증명 이후 검토

### 4.3 Break-Even 분석

Free tier 비용 제한 적용 후:

| 시나리오 | 총 유저 | Free 비용 | Pro 유저 (10%) | Pro 비용 | 고정비 | 총비용 | 수익 ($8×Pro) | 손익 |
|---------|--------|----------|--------------|---------|-------|--------|-------------|------|
| 초기 | 50 | $22 | 5 | $15 | $30 | $67 | $40 | -$27 |
| 안정 | 150 | $60 | 15 | $45 | $55 | $160 | $120 | -$40 |
| BEP 근접 | 300 | $120 | 30 | $90 | $55 | $265 | $240 | -$25 |
| 흑자 | 400 | $150 | 45 | $135 | $55 | $340 | $360 | +$20 |
| 안정 흑자 | 500 | $175 | 55 | $165 | $55 | $395 | $440 | +$45 |

**Pro 유저 약 40-50명 (총 유저 400-500명, 전환율 10%)에서 운영비 자급자족 달성.**

10% 전환율은 일반 SaaS 평균(2-5%)보다 높지만, niche tool + strong personalization이면 달성 가능한 범위다.

### 4.4 전환율을 올리는 핵심 — "4주의 벽"

```
Week 1:  문서 3개 ingest → S1 summary
         → "오, 요약 괜찮네"

Week 2:  첫 S2 + recommendation
         → "내 관심사를 어느 정도 맞추네"

Week 3:  Feedback 반영된 recommendation
         → "어, 저번보다 낫다?"

Week 4:  Free ingest 한도에 도달
         → "더 넣고 싶은데..."
         → 이 순간이 conversion moment
```

**Recommendation이 "정말 나를 안다"고 느끼는 순간이 conversion trigger.** 그래서 recommendation과 summary를 무료로 여는 것이 핵심이다. 사용자가 value를 충분히 느낀 뒤에 limit에 부딪혀야 한다.

### 4.5 추가 Pro 전환 trigger (향후)

| 기능 | 기반 | 시점 |
|------|------|------|
| Custom keywords → recommendation tuning | Post-MVP #1 user_keywords | alpha 이후 |
| Recommendation history 전체 열람 | 현재 recommendations 테이블 | 바로 가능 |
| Summary/notes export (Markdown/CSV) | 현재 notes/summaries 테이블 | 바로 가능 |
| Multiple interest tracks | user_interest_profiles 기반 | profile layer 이후 |
| Advanced RAG (topic filter, citation depth) | 현재 RAG router 확장 | 중기 |

### 4.6 결제 구현

| 옵션 | 장점 | 단점 | 추천 시점 |
|------|------|------|----------|
| **RevenueCat** (Android in-app) | Google Play subscription 관리, free tier로 월 $2.5K 수익까지 무료 | 모바일 전용 | Android 우선이면 1순위 |
| **Stripe Checkout** | 업계 표준, web 결제, 2.9% + 30¢/건 | 모바일 외 web interface 필요 | web 추가 시 |
| **LemonSqueezy** | Stripe보다 간단, 세금 자동 처리 | 5% + 50¢/건 (다소 비쌈) | 빠른 구현 원할 때 |

추천: Android 앱이 주력이면 **RevenueCat으로 Google Play subscription** 우선. Web에서도 받고 싶으면 **Stripe Checkout 병행.**

### 4.7 다른 수익 모델 검토

| 모델 | 적합성 | 비고 |
|------|--------|------|
| **Freemium SaaS** | ★★★★★ | 위 설계. 두 경로 모두 최적 |
| **Usage-based** ($0.10/doc, $0.05/query) | ★★★☆☆ | Cost-revenue가 linear하게 align되지만, 사용자가 cost를 의식해 사용을 줄이면 data flywheel이 약해짐 |
| **One-time purchase** | ★★☆☆☆ | 운영비가 지속 발생하므로 구독이 더 적합 |
| **B2B / Enterprise** (연간 lab 라이센스) | ★★★☆☆ | PMF 이후 VC 경로에서만 의미. $500-2K/year per lab |
| **Marketplace** (curated reading list 판매) | ★★☆☆☆ | 장기 비전으로만 검토. 초기에는 복잡도만 증가 |
| **Open-source + hosted** | ★★★★☆ | Personal branding에 최적이나 수익화가 어려움. Core open + managed hosting(Pro)은 하이브리드로 가능 |

---

## 5. Launch 채널 (두 경로 공통, 우선순위순)

| # | 채널 | 방법 | VC 경로 | Indie 경로 |
|---|------|------|---------|-----------|
| 1 | **Twitter/X ML Community** | "I built a personal learning assistant that learns my research interests over time" thread + demo GIF | 필수 | 필수 |
| 2 | **Hacker News (Show HN)** | "Show HN: Personal Learning Assistant with Episodic-Semantic Memory" + 기술 블로그 | 필수 | 매우 효과적 |
| 3 | **Technical blog** | 시리즈 포스트 (§3.4 참조) | 선택 | 필수 (branding 핵심) |
| 4 | **Product Hunt** | 좋은 demo video가 핵심 | 필수 | 선택 |
| 5 | **Reddit** | r/MachineLearning, r/PhD, r/ArtificialIntelligence | 효과적 | 효과적 |
| 6 | **LinkedIn** | Professional 톤, lessons learned | 선택 | 필수 (career 채널) |
| 7 | **arXiv 관련 Discord** | Papers with Code, ML Collective, EleutherAI | 효과적 | 효과적 |

---

## 6. 권장 Timeline

### Track A — VC 경로

| 기간 | 목표 | 핵심 액션 |
|------|------|----------|
| Month 1-2 | Closed alpha | 10-30명 ML 연구자 recruit. Retention/recommendation quality metric 수집 |
| Month 3-4 | Public beta + iOS/Web | Product Hunt, HN, Twitter launch. 추천 소스 확장 시작 |
| Month 5-6 | Growth + Fundraise | Retention data 기반 seed pitch. 팀 빌딩 |

### Track B — Indie / Branding 경로

| 기간 | 목표 | 핵심 액션 |
|------|------|----------|
| Month 1 | Closed alpha + 블로그 #1 | 10명 alpha. "Why I Built This" 포스트 |
| Month 2 | 블로그 #2-3 + GitHub 정리 | Memory architecture, recommendation 포스트. README 재작성 |
| Month 3 | Public beta + Show HN | Twitter thread, HN launch. Freemium tier 적용 |
| Month 4+ | 운영 + 개선 + 블로그 #4 | Feedback 기반 품질 튜닝. "What I Learned" retrospective 포스트 |

---

## 7. 핵심 가설과 검증 기준

두 경로 모두에서 가장 중요한 가설:

> **"사용자가 4주 이상 사용하면, 추천 품질이 체감 가능하게 좋아지는가?"**

이것이 증명되면:
- VC 경로: product-market fit의 가장 강력한 신호
- Indie 경로: 블로그/데모의 가장 설득력 있는 콘텐츠

검증 metric:

| Metric | 측정 방법 | 목표 |
|--------|----------|------|
| D7 / D30 retention | 7일/30일 후 재방문 | D7 > 40%, D30 > 20% |
| Weekly engagement | 주 1회 이상 ingest 또는 recommendation 확인 | > 60% of active users |
| Recommendation precision | thumbs up / (thumbs up + thumbs down) | > 60%, 4주 후 > 70% |
| Feedback participation | 추천 받은 유저 중 feedback을 준 비율 | > 30% |
| Recommendation improvement | Week 1 vs Week 4 precision 비교 | 통계적으로 유의한 향상 |

---

## 8. 요약

| 관점 | VC 경로 | Indie / Branding 경로 |
|------|---------|----------------------|
| **목표** | 빠른 성장, 투자 유치, 시장 점유 | 운영비 자급자족, personal brand, 실서비스 운영 경험 |
| **필수 조건** | iOS/Web, 추천 소스 확장, 팀, retention 증명 | 블로그 시리즈, GitHub 정리, closed alpha |
| **수익 모델** | Freemium → Team/Enterprise | Freemium (Free + Pro $8/mo) |
| **BEP** | 빠른 성장으로 BEP보다 GMV/ARR 우선 | Pro 유저 ~45명 (총 ~400명) |
| **리스크** | 높음 (경쟁, 자금, 팀) | 낮음 (어떤 결과든 career asset) |
| **결과** | 성공 시 사업, 실패 시 학습 | 성공 시 사업화 가능, "실패"해도 포트폴리오 + 운영 경험 |

**두 경로는 상호 배타적이지 않다.** Indie/branding 경로로 시작하여 traction이 보이면 VC 경로로 전환할 수 있고, 그렇지 않더라도 personal brand와 운영 경험이 남는다.

---

*문서 작성: 2026-03 기준. 비용 추정은 OpenAI/Supabase/Cloud Run 현재 요금 기준이며, 실제 사용 패턴에 따라 달라질 수 있다.*
