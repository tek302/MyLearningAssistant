# LLM Usage Inventory & Model Strategy

**Date:** 2026-03-22  
**Purpose:** Prompt tuning, 모델 전환, 비용 최적화 시 참고용. 모든 LLM call site, 프롬프트 구조, 모델 비교, 전환 시나리오를 한 곳에 정리.

---

## Environment Variables (LLM 관련)

### Core

| Variable | Default | Role |
|----------|---------|------|
| `OPENAI_API_KEY` | (required) | OpenAI API 인증 |
| `LLM_PROVIDER` | `openai` | Chat completion provider: `openai` 또는 `gemini` |
| `GEMINI_API_KEY` | — | Gemini 사용 시 필수 |
| `SUMMARY_MODEL` | — (global fallback) | 함수별 env var 미설정 시 전체 fallback |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding 모델 (항상 OpenAI) |
| `JUDGE_ENABLED` | `false` | Judge node 활성화 여부 |
| `S2_SUMMARY_VERSION` | `v2` | S2 함수 선택: `v1` → `create_s2_summary`, `v2` → `create_s2_summary_v2` |
| `S1_TLDR_MAX_CHARS` | `150` | S1 tldr 최대 길이 |
| `S1_BULLETS_COUNT` | `3` | S1 bullet 개수 (1–7 clamped) |

### Per-function model env vars (신규 — `app/utils/llm_client.py`에서 관리)

Resolution 우선순위: 함수별 env var → `SUMMARY_MODEL` → hardcoded default.

| Variable | Hardcoded Default | 대상 함수 |
|----------|:-----------------:|-----------|
| `S1_MODEL` | **gpt-4.1** | `create_s1_summary` |
| `S2_MODEL` | **gpt-4.1** | `create_s2_summary` / `create_s2_summary_v2` |
| `KEYWORD_EXPANSION_MODEL` | **gpt-4.1** | `run_keyword_expansion` |
| `RAG_SYNTHESIS_MODEL` | **gpt-4.1-mini** | `node_synthesize_answer` / `node_retry_synthesize` / `RAGService._synthesize_answer` |
| `JUDGE_MODEL` | **gpt-4.1-mini** | `judge_answer` |
| `RAG_REWRITE_MODEL` | **gpt-4.1-mini** | `rewrite_query` |

---

## 1. S1 Summary — `create_s1_summary`

| 항목 | 값 |
|------|-----|
| **파일** | `app/utils/summarization.py` |
| **호출 경로** | `job_runner.py` → `run_pdf_worker._create_s1_summary_for_source` / `ingest_graph.py` |
| **모델** | `S1_MODEL` (default **gpt-4.1**) |
| **Temperature** | `0.3` |
| **max_tokens** | 미설정 |
| **response_format** | `{"type": "json_object"}` |
| **Retry** | 최대 2회 (exponential backoff) |

**System prompt:**
```
You are a helpful assistant that creates concise summaries in JSON format.
```

**User prompt (template):**
```
Summarize the following text in JSON.

1. tldr: ONE short sentence only (max {tldr_max} characters). No multiple sentences.
2. bullets: Exactly {bullets_count} key points. Each point one short phrase or sentence.
3. tags: Optional, max 6 comma-separated keywords.

Text content:
{chunks_text}

Respond in JSON only:
{
  "tldr": "one sentence summary here",
  "bullets": ["key point 1", "key point 2", "key point 3"],
  "tags": ["tag1", "tag2"]
}
```

**Input truncation:** 없음 (chunks_text는 상위 N chunks, `S1_MAX_CHUNKS` default 8)  
**Output parsing:** `json.loads` → tldr 길이 truncate, bullets 개수 제한, tags 6개 제한  
**반환:** `{tldr, bullets, tags}`

---

## 2. S2 Summary v1 — `create_s2_summary`

| 항목 | 값 |
|------|-----|
| **파일** | `app/utils/summarization.py` |
| **호출 경로** | `s2_consolidation.py` → `run_s2_consolidation` (when `S2_SUMMARY_VERSION=v1`) |
| **모델** | `S2_MODEL` (default **gpt-4.1**) |
| **Temperature** | `0.3` |
| **max_tokens** | 미설정 |
| **response_format** | `{"type": "json_object"}` |
| **Retry** | 최대 2회 |

**System prompt:**
```
You are a helpful assistant that creates concise technical summaries in JSON format.
```

**User prompt (template):**
```
You are summarizing the key technical points from multiple documents read this week.
Below is a concatenation of one-sentence summaries and bullet points from each document.

Produce a single weekly summary in JSON:
1. tldr: ONE short sentence (max 200 chars) capturing the main theme of the week's reading.
2. bullets: Between 5 and 15 technical points that are the most important across all documents.
   Each point one short phrase or sentence.

Combined document summaries:
{combined_s1_text[:12000]}

Respond in JSON only:
{
  "tldr": "one sentence weekly summary",
  "bullets": ["point 1", "point 2", "point 3", ...]
}
```

**Input truncation:** `combined_s1_text[:12000]`  
**Output parsing:** tldr 300자 truncate, bullets 최대 15개  
**반환:** `{tldr, bullets}`

---

## 3. S2 Summary v2 — `create_s2_summary_v2`

| 항목 | 값 |
|------|-----|
| **파일** | `app/utils/summarization.py` |
| **호출 경로** | `s2_consolidation.py` → `_run_s2_v2` (when `S2_SUMMARY_VERSION=v2`, default) |
| **모델** | `S2_MODEL` (default **gpt-4.1**) |
| **Temperature** | `0.4` |
| **max_tokens** | 미설정 |
| **response_format** | `{"type": "json_object"}` |
| **Retry** | 최대 2회 |

**System prompt:**
```
You are a personal learning advisor that produces structured weekly reading summaries in JSON.
```

**User prompt (`_build_s2_v2_prompt`):**  
조건부로 4개 블록이 조립됨:

1. **Keyword instruction** (keywords ≥ 1):
   ```
   The user's active research keywords (ordered by importance):
   {keyword_list}

   Organize the summary into SECTIONS, one per keyword that appeared in this week's reading.
   If a document's content does not match any keyword, include it under an appropriate keyword
   or list the topic in "emerging_topics".
   ```
   (keywords = 0일 때): LLM이 직접 topic 추출하여 sections 생성, emerging_topics에 표시

2. **Notes block** (있으면): `notes_text[:1500]`

3. **Feedback block** (있으면): `feedback_text[:1000]`

4. **S1 text**: `s1_text[:10000]`

5. **Trajectory block** (prev S2 있으면): `prev_s2_text[:3000]` + deepened/new_this_week/paused 비교 지시. 없으면 trajectory = null.

**Output schema:**
```json
{
  "tldr": "...(max 250 chars, second person)",
  "bullets": ["5-10 flat points"],
  "sections": [{"keyword": "...", "insights": ["..."], "doc_count": N}],
  "emerging_topics": ["..."],
  "connections": [{"docs": ["A", "B"], "insight": "..."}],
  "trajectory": {"deepened": ["..."], "new_this_week": ["..."], "paused": ["..."]},
  "reflection": "1-2 sentences, second person"
}
```

**Input truncation:** s1_text 10K, notes 1.5K, feedback 1K, prev_s2 3K  
**Output parsing:** `_parse_s2_v2_result` — sections 10개, insights 4개/section, emerging 10개, connections 5개, trajectory 5개/group, reflection 500자  
**반환:** `{tldr, bullets, sections, emerging_topics, connections, trajectory, reflection}`

---

## 4. RAG Synthesis — `node_synthesize_answer`

| 항목 | 값 |
|------|-----|
| **파일** | `app/graphs/rag_graph.py` |
| **호출 경로** | RAG LangGraph → synthesize node |
| **모델** | `RAG_SYNTHESIS_MODEL` (default **gpt-4.1-mini**) |
| **Temperature** | `0.3` |
| **max_tokens** | `1000` |
| **response_format** | 미설정 (free text) |
| **Retry** | 없음 (별도 retry node 존재) |

**System prompt:**
```
You are a helpful assistant that provides accurate answers with proper citations.
```

**User prompt (template):**
```
You are a helpful assistant that answers questions based on the provided context.

Context (from {num_chunks} document chunks):
{context_text}

Question: {query}

Instructions:
1. Answer the question based ONLY on the context provided. Do not use any external knowledge
   or make assumptions.
2. When referencing information from the context, use citation markers [1], [2], [3], etc.
3. The citations correspond to the chunks in order (first chunk is [1], second is [2], etc.).
4. Be concise but comprehensive.
5. CRITICAL: If the context doesn't contain enough information to answer the question,
   you MUST say so clearly. Do not guess or make up information.
6. CRITICAL: Do not include citation markers for information that is not in the context.
7. If you cannot answer the question based on the context, respond with:
   "I cannot answer this question based on the provided context."

Answer:
```

**Post-processing:** citation marker `[N]` 없으면 suffix 자동 추가. `_is_cannot_answer` 패턴 체크.  
**반환:** `state.answer` (string)

---

## 5. RAG Retry Synthesis — `node_retry_synthesize`

| 항목 | 값 |
|------|-----|
| **파일** | `app/graphs/rag_graph.py` |
| **호출 경로** | RAG LangGraph → eval fail → retry node |
| **모델** | `RAG_SYNTHESIS_MODEL` (default **gpt-4.1-mini**) |
| **Temperature** | `0.0` (deterministic) |
| **max_tokens** | `800` |
| **response_format** | 미설정 (free text) |

**System prompt:**
```
You are a helpful assistant that provides accurate answers with proper citations.
Always include citation markers [1], [2], etc. when referencing the context.
```

**User prompt:** Synthesis와 동일 구조, citation 필수 강조:
```
...
4. Rewrite to include correct citation markers [1]...[{num_chunks}].
   If not possible, say "I cannot answer this question based on the provided context."
...
```

**Post-processing:** Synthesis와 동일 (marker suffix + cannot_answer)  
**반환:** `state.answer` (string), `state.attempt` increment

---

## 6. RAG Service Synthesis — `RAGService._synthesize_answer`

| 항목 | 값 |
|------|-----|
| **파일** | `app/services/rag_service.py` |
| **호출 경로** | Legacy RAG service (non-graph path) |
| **모델** | `RAG_SYNTHESIS_MODEL` (default **gpt-4.1-mini**) |
| **Temperature** | `0.3` |
| **max_tokens** | `1000` |
| **response_format** | 미설정 (free text) |

**프롬프트:** `node_synthesize_answer`와 동일.  
**비고:** Graph path (#4)와 중복 — legacy path. Graph가 primary.

---

## 7. Keyword Expansion (Stage 1) — `run_keyword_expansion`

| 항목 | 값 |
|------|-----|
| **파일** | `app/services/keyword_expansion.py` |
| **호출 경로** | `job_runner.py` → S2 완료 후 `_run_keyword_pipeline_after_s2` → `stage1_keyword_expansion` job |
| **모델** | `KEYWORD_EXPANSION_MODEL` (default **gpt-4.1**) |
| **Temperature** | `0.7` (creative) |
| **max_tokens** | `500` |
| **response_format** | 미설정 (JSON array 기대) |
| **System prompt** | 없음 (user message only) |

**User prompt (`_build_stage1_prompt`):**
```
You are a research advisor. Based on the user's current research keyword set and recent
learning activity, suggest exactly 3 new research keywords they should explore.

Each suggestion must be one of these types:
- derivative: a keyword derived from an existing keyword (specify parent)
- emerging: a topic gaining traction in the user's research area
- cross_domain: a keyword connecting two different areas the user studies
- deepening: a more specific sub-topic of an existing keyword (specify parent)

Current keyword set:
- {keyword} (weight={weight}, source={source})
...

Recent weekly summary (S2):
{s2_text[:2000]}

Recent notes:
{notes_text[:1500]}

{rejected recently 목록}

Respond with a JSON array of exactly 3 objects:
[
  {"keyword": "...", "parent_keyword": "..." or null, "type": "...",
   "reason": "one sentence why", "confidence": 0.0-1.0}
]

Only return the JSON array, no other text.
```

**Input truncation:** s2_text 2K, notes_text 1.5K  
**Output parsing:** `json.loads` + bracket substring fallback. 기존 keyword/rejected와 중복 제거.  
**반환:** `(suggestion_ids, error_or_None)`

---

## 8. RAG Judge — `judge_answer`

| 항목 | 값 |
|------|-----|
| **파일** | `app/rag/nodes/judge.py` |
| **호출 경로** | RAG LangGraph → judge node (when `JUDGE_ENABLED=true`) |
| **모델** | `JUDGE_MODEL` (default **gpt-4.1-mini**) |
| **Temperature** | `0` (deterministic) |
| **max_tokens** | 미설정 |
| **response_format** | `{"type": "json_object"}` |

**System prompt:**
```
You are an expert evaluator. Respond only with valid JSON.
```

**User prompt (template):**
```
You are an expert evaluator assessing the quality of an AI-generated answer.

Question: {query}

Context excerpts (with citation IDs):
[1] {excerpt_text[:1000]}
[2] ...

Answer to evaluate:
{answer_text}

Evaluate the answer on three dimensions (each scored 0.0 to 1.0):

1. **faithfulness**: How faithful is the answer to the provided context?
   - Hallucination => heavy penalty (0.0-0.3)
   - Minor inaccuracies => moderate penalty (0.4-0.6)
   - Mostly faithful => good score (0.7-0.9)
   - Perfectly faithful => 1.0

2. **coverage**: How well does the answer address the user's question?
   ...

3. **citation_correctness**: Are citation markers [1], [2], etc. used correctly?
   ...

4. **overall**: Weighted average = 0.50*faithfulness + 0.35*coverage + 0.15*citation_correctness

Provide 1-4 brief reasons (each <= 80 characters) explaining your scores.

Respond ONLY with valid JSON:
{
  "faithfulness": 0.85,
  "coverage": 0.90,
  "citation_correctness": 0.80,
  "overall": 0.86,
  "reasons": ["Reason 1", "Reason 2"]
}
```

**Output parsing:** `json.loads` + `_extract_json_from_text` fallback → `JudgeResult` Pydantic model  
**Judge thresholds (env):** `JUDGE_THRESHOLD_OVERALL=0.75`, `JUDGE_THRESHOLD_FAITHFULNESS=0.80`, `JUDGE_THRESHOLD_COVERAGE=0.70`  
**반환:** `state.judge` (`JudgeResult`), `state.judge_phase` (pre/post)

---

## 9. Query Rewrite — `rewrite_query`

| 항목 | 값 |
|------|-----|
| **파일** | `app/rag/nodes/rewrite_query.py` |
| **호출 경로** | RAG LangGraph → refine strategy `rewrite_query` |
| **모델** | `RAG_REWRITE_MODEL` (default **gpt-4.1-mini**) |
| **Temperature** | `0` (deterministic) |
| **max_tokens** | 미설정 |
| **response_format** | `{"type": "json_object"}` |

**System prompt:**
```
You are a helpful assistant that rewrites queries for better information retrieval.
Respond only with valid JSON.
```

**User prompt (template):**
```
Rewrite the following search query to improve retrieval of relevant information,
while preserving the user's original intent.

Original query: {original_query}

Requirements:
- Preserve the user's intent exactly. Do not add new requirements or change the meaning.
- Make the query more specific and clear for information retrieval.
- Keep it concise (maximum 2 sentences).
- Focus on key terms that would help find relevant documents.

Respond ONLY with valid JSON in this exact format:
{
  "rewritten_query": "<rewritten query text>"
}
```

**Output parsing:** `json.loads` + `_extract_json_from_text` fallback. 실패 시 원본 query 유지.  
**반환:** `state.query_current` (rewritten string)

---

## 10. Embeddings — `create_embeddings`

| 항목 | 값 |
|------|-----|
| **파일** | `app/utils/embeddings.py` |
| **호출 경로** | Ingest (chunk embedding), RAG (query embedding) |
| **API** | `client.embeddings.create(model=model, input=texts)` |
| **모델** | `EMBEDDING_MODEL` (default `text-embedding-3-small`) |
| **Dimensions** | 1536 (text-embedding-3-small default) |
| **Retry** | 최대 2회 (exponential backoff) |
| **반환** | `List[List[float]]` |

---

## Summary Table

| # | Function | Purpose | Model (default) | purpose key | Temp | max_tokens | response_format | Input Limit |
|---|----------|---------|:---------------:|:-----------:|:----:|:----------:|:---------------:|-------------|
| 1 | `create_s1_summary` | Document S1 요약 | **gpt-4.1** | `s1_summary` | 0.3 | — | json_object | S1_MAX_CHUNKS (8) |
| 2 | `create_s2_summary` (v1) | Weekly S2 요약 | **gpt-4.1** | `s2_summary` | 0.3 | — | json_object | 12K chars |
| 3 | `create_s2_summary_v2` | Weekly S2 구조화 요약 | **gpt-4.1** | `s2_summary` | 0.4 | — | json_object | 10K+1.5K+1K+3K |
| 4 | `node_synthesize_answer` | RAG 답변 생성 | **gpt-4.1-mini** | `rag_synthesis` | 0.3 | 1000 | — | context_text |
| 5 | `node_retry_synthesize` | RAG 재시도 (strict) | **gpt-4.1-mini** | `rag_retry` | 0.0 | 800 | — | context_text |
| 6 | `RAGService._synthesize_answer` | RAG legacy | **gpt-4.1-mini** | `rag_synthesis` | 0.3 | 1000 | — | context_text |
| 7 | `run_keyword_expansion` | Stage 1 keyword 제안 | **gpt-4.1** | `keyword_expansion` | 0.7 | 500 | — | 2K+1.5K |
| 8 | `judge_answer` | RAG 답변 품질 평가 | **gpt-4.1-mini** | `rag_judge` | 0.0 | — | json_object | excerpts 1K/chunk |
| 9 | `rewrite_query` | RAG query 개선 | **gpt-4.1-mini** | `rag_rewrite` | 0.0 | — | json_object | original_query |
| 10 | `create_embeddings` | Vector embedding | text-embedding-3-small | — | — | — | — | texts batch |

---

## Cost Estimate (per event, gpt-4o-mini pricing $0.15/1M input, $0.60/1M output)

| Function | ~Input tokens | ~Output tokens | ~Cost/call |
|----------|---------------|----------------|------------|
| S1 summary | 1–3K | 200–400 | $0.0004 |
| S2 v1 | 2–3K | 300 | $0.0005 |
| S2 v2 | 4–5K | 800 | $0.001 |
| RAG synthesis | 2–6K | 300–500 | $0.0006 |
| RAG retry | 2–6K | 300–500 | $0.0006 |
| Keyword expansion | 1–2K | 300 | $0.0004 |
| Judge | 2–4K | 100–200 | $0.0004 |
| Query rewrite | 200 | 50 | $0.00005 |
| Embedding | varies | — | $0.02/1M tokens |

---

## Prompt Version Tracking

| Context | Version Field | Location |
|---------|---------------|----------|
| S1 summary | — (unversioned) | `summaries.extra` |
| S2 summary | `summaries.extra.prompt_version` | `s2-summary-v1` / `s2-summary-v2` |
| Keyword expansion | `recommendation_generation_runs.meta.prompt_version` | `stage1-v1` |
| RAG judge | — (logged in `rag_events`) | `model` field |

---

---

# Part 2: Model Comparison & Migration Strategy

## Available Models (2026-03 pricing, per 1M tokens)

### OpenAI

| Model | Input | Output | Context | 특성 |
|-------|------:|-------:|--------:|------|
| gpt-4.1-nano | $0.10 | $0.40 | 1M | 최저가. 단순 extraction 충분 |
| **gpt-4o-mini** (현재) | **$0.15** | **$0.60** | **128K** | **현재 전 call site 사용** |
| gpt-4.1-mini | $0.40 | $1.60 | 128K | instruction following 향상 |
| gpt-4.1 | $2.00 | $8.00 | 1M | 2026 production 추천 모델. reasoning + instruction 최상위 |
| gpt-4o (legacy) | $2.50 | $10.00 | 128K | gpt-4.1에 대체됨 |

### Google Gemini

| Model | Input | Output | Context | 특성 |
|-------|------:|-------:|--------:|------|
| Gemini 2.0 Flash | $0.10 | $0.40 | 1M | gpt-4o-mini 대비 저렴. max output 8K |
| Gemini 2.5 Flash | $0.30 | $2.50 | 1M | reasoning 포함. max output 64K |
| Gemini 2.5 Pro | $1.25 | $10.00 | 2M | 최고 reasoning. max output 64K |

### Anthropic Claude

| Model | Input | Output | Context | 특성 |
|-------|------:|-------:|--------:|------|
| Claude Haiku 3 (legacy) | $0.25 | $1.25 | 200K | 저렴하지만 구세대 |
| Claude Haiku 4.5 | $1.00 | $5.00 | 200K | mid-tier |
| Claude Sonnet 4.6 | $3.00 | $15.00 | 200K | high-quality reasoning |

### 대응 관계

| Tier | OpenAI | Gemini | 역할 |
|------|--------|--------|------|
| Budget | gpt-4o-mini ($0.15/$0.60) | Gemini 2.0 Flash ($0.10/$0.40) | 단순 extraction, rewrite |
| Mid | gpt-4.1-mini ($0.40/$1.60) | Gemini 2.5 Flash ($0.30/$2.50) | RAG synthesis |
| High | gpt-4.1 ($2.00/$8.00) | Gemini 2.5 Pro ($1.25/$10.00) | S2 구조화, keyword expansion |

---

## 월간 비용 시뮬레이션 (주 3.5 ingest 기준)

### 월간 호출량 추정

| Function | 월 호출 | ~Input tokens/call | ~Output tokens/call | 월 Input total | 월 Output total |
|----------|--------:|-------------------:|--------------------:|---------------:|----------------:|
| S1 summary | 14 | 2K | 300 | 28K | 4.2K |
| S2 v2 summary | 4 | 5K | 800 | 20K | 3.2K |
| Keyword expansion | 4 | 2K | 300 | 8K | 1.2K |
| RAG synthesis | 30 | 4K | 400 | 120K | 12K |
| RAG retry | 5 | 4K | 400 | 20K | 2K |
| Judge | 30 | 3K | 150 | 90K | 4.5K |
| Query rewrite | 10 | 200 | 50 | 2K | 0.5K |
| **Total** | | | | **288K** | **27.6K** |

### 시나리오별 월 비용

#### A. 전부 Budget 모델 (단일 모델)

| 시나리오 | Input cost | Output cost | **합계** |
|----------|----------:|----------:|--------:|
| **현재**: 전부 gpt-4o-mini | $0.043 | $0.017 | **$0.06** |
| 전부 Gemini 2.0 Flash | $0.029 | $0.011 | **$0.04** |

#### B. 차등 모델 (고 impact → 고급, 저 impact → Budget)

**함수별 모델 배정 (확정, 2026-03-22):**

| Function | Impact | GPT **확정** | Gemini 대응 |
|----------|:------:|:------------:|-------------|
| S1 summary | **높음** | **gpt-4.1** | Gemini 2.5 Pro |
| S2 v2 summary | **높음** | **gpt-4.1** | Gemini 2.5 Pro |
| Keyword expansion | **높음** | **gpt-4.1** | Gemini 2.5 Pro |
| RAG synthesis/retry | 중간 | **gpt-4.1-mini** | Gemini 2.5 Flash |
| Judge | 중간 | **gpt-4.1-mini** | Gemini 2.0 Flash |
| Query rewrite | 중간 | **gpt-4.1-mini** | Gemini 2.0 Flash |

**비용 비교:**

| Function | Tokens (in/out) | GPT 차등 | Gemini 차등 |
|----------|:---:|---:|---:|
| S2 v2 (High) | 20K / 3.2K | $0.066 | $0.057 |
| Keyword (High) | 8K / 1.2K | $0.026 | $0.022 |
| RAG synth+retry (Mid) | 140K / 14K | $0.078 | $0.077 |
| S1 (Budget) | 28K / 4.2K | $0.005 | $0.005 |
| Judge (Budget) | 90K / 4.5K | $0.016 | $0.011 |
| Rewrite (Budget) | 2K / 0.5K | ~$0 | ~$0 |
| **합계** | | **$0.19** | **$0.17** |

#### 전체 비교 요약

| 시나리오 | 월 비용 | 대비 현재 |
|----------|--------:|:---------:|
| **현재** — 전부 gpt-4o-mini | $0.06 | — |
| A — 전부 Gemini 2.0 Flash | $0.04 | -33% |
| B-GPT — 차등 (4.1 + 4.1-mini + nano) | $0.19 | +$0.13 |
| B-Gemini — 차등 (2.5 Pro + Flash + 2.0 Flash) | $0.17 | +$0.11 |
| 극단 — 전부 gpt-4.1 | $0.80 | +$0.74 |

> **결론:** 월 $0.20 미만이라 비용은 사실상 무의미한 차이. 선택 기준은 품질과 구현 편의.

---

## Gemini 전환 가이드

### OpenAI SDK 호환 endpoint

Gemini가 OpenAI SDK 호환 endpoint를 제공하므로, **SDK 교체 없이** 설정 변경만으로 전환 가능:

```python
# Before (OpenAI)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# After (Gemini via OpenAI SDK)
client = OpenAI(
    api_key=os.getenv("GEMINI_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)
```

`client.chat.completions.create()`, `response_format: {"type": "json_object"}` 모두 그대로 동작.

### 전환 시 환경변수 (예시)

```env
# Provider 선택
LLM_PROVIDER=gemini                # "openai" 또는 "gemini"

# Gemini 인증
GEMINI_API_KEY=AIza...

# 모델명 (Gemini)
SUMMARY_MODEL=gemini-2.0-flash     # budget (S1, judge, rewrite)
S2_MODEL=gemini-2.5-pro            # S2 v2 전용
KEYWORD_EXPANSION_MODEL=gemini-2.5-pro  # Stage 1 전용
RAG_SYNTHESIS_MODEL=gemini-2.5-flash    # RAG 답변 전용

# Embeddings는 OpenAI 유지 (re-embed 방지)
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-...
EMBEDDING_MODEL=text-embedding-3-small
```

### 구현 변경 범위 — DONE (2026-03-22)

| 변경 | 내용 | 상태 |
|------|------|:------:|
| `app/utils/llm_client.py` 신규 | `get_chat_client()`, `get_embedding_client()`, `get_model(purpose)` | **완료** |
| 모델명 env var 분리 | 함수별 `S1_MODEL`, `S2_MODEL`, `KEYWORD_EXPANSION_MODEL`, `RAG_SYNTHESIS_MODEL`, `JUDGE_MODEL`, `RAG_REWRITE_MODEL` | **완료** |
| Provider 분기 | `LLM_PROVIDER` env에 따라 OpenAI/Gemini `base_url` 분기 | **완료** |
| Embeddings 분리 | `get_embedding_client()` — 항상 OpenAI | **완료** |

**수정된 파일:**

| 파일 | 변경 내용 |
|------|-----------|
| `app/utils/llm_client.py` | 신규 — 중앙 client factory + per-function model config |
| `app/utils/summarization.py` | `get_chat_client()` + `get_model("s1_summary"/"s2_summary")` 전환 |
| `app/utils/embeddings.py` | `get_embedding_client()` 전환 |
| `app/services/keyword_expansion.py` | `get_chat_client()` + `get_model("keyword_expansion")` 전환 |
| `app/services/rag_service.py` | `get_chat_client()` + `get_model("rag_synthesis")` 전환 |
| `app/services/s2_consolidation.py` | `get_model("s2_summary")` 전환 |
| `app/graphs/rag_graph.py` | `get_chat_client()` + `get_model("rag_synthesis"/"rag_retry")` 전환 |
| `app/rag/nodes/rewrite_query.py` | `get_model("rag_rewrite")` 전환 |
| `app/rag/nodes/judge.py` | (config.py 경유) `get_model("rag_judge")` 전환 |
| `app/config.py` | `get_judge_model()` → `llm_client.get_model("rag_judge")` 위임 |

### 주의사항

1. **Embeddings는 분리 유지** — Gemini embedding (`text-embedding-004`)은 OpenAI와 차원이 다름. 전환 시 DB의 모든 벡터를 re-embed 해야 하므로, chat completion만 Gemini로 전환하고 embedding은 OpenAI 유지 권장.

2. **모델명 매핑** — Gemini 모델명은 `gemini-2.0-flash`, `gemini-2.5-flash`, `gemini-2.5-pro` 형태. 환경변수에서 관리.

3. **AI Studio free tier 제한** — RPM/TPM 제한이 있을 수 있음. 기존 retry 로직이 rate limit 에러도 처리하므로 큰 문제 없음.

4. **Gemini 2.0 Flash max output = 8K tokens** — 현재 모든 call site의 output이 1K 미만이므로 문제 없음.

5. **하이브리드 가능** — `get_chat_client(model)` 함수에서 모델명 prefix로 provider 자동 판별 가능 (`gemini-*` → Gemini endpoint, `gpt-*` → OpenAI endpoint). GPT와 Gemini를 섞어 쓰는 것도 가능.

---

## 전환 로드맵

| 단계 | 내용 | 상태 |
|------|------|:------:|
| **1** | `llm_client.py` factory + per-function model config + 전 call site 전환 | **완료** (2026-03-22) |
| **1b** | 차등 모델 적용: S1/S2/Keyword → gpt-4.1, 나머지 → gpt-4.1-mini | **완료** (2026-03-22) |
| **2** | BE 배포 후 품질 확인 | 다음 |
| **3** | (선택) Gemini free tier 사용 시 env var만 변경하여 전환 | — |
| **4** | (선택) 전체 Gemini 안정화 후 OpenAI 의존 제거 검토 (embeddings 제외) | — |

---

*2026-03-22: 전체 LLM usage inventory 작성. 9개 chat completion call site + 1 embedding call site.*  
*2026-03-22: Model comparison & migration strategy 추가. GPT vs Gemini 비용 시뮬레이션, 차등 모델 전략, Gemini 전환 가이드.*  
*2026-03-22: **최종 결정** — S1/S2/Keyword → gpt-4.1, RAG/Judge/Rewrite → gpt-4.1-mini, Embedding → text-embedding-3-small (유지). `app/utils/llm_client.py` 신규 생성, 10개 파일 전환 완료.*
