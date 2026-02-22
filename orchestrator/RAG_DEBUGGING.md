# RAG "I cannot answer" 디버깅 가이드

RAG가 "I cannot answer this question based on the provided context" 를 반환할 때 원인을 찾는 방법입니다.

## 원인 요약

- **Citations [1][2][3][4]가 있어도** 이 메시지가 나오면, **LLM이 받은 context를 보고 “답할 수 없다”고 판단**한 경우입니다.
- 코드에서 “cannot answer” 문구 뒤에 `Sources: [1][2][3][4]` 를 자동으로 붙이기 때문에, citations가 있어도 실제로는 **모델이 거절 응답**을 한 것입니다.

---

## 1. 응답 `meta` 확인

응답의 `meta` 필드로 흐름을 구분할 수 있습니다.

```powershell
$r = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/rag/answer" `
  -Headers @{ Authorization="Bearer $env:ID_TOKEN" } `
  -ContentType "application/json" `
  -Body '{"query":"Summarize the document in 5 bullets","top_k":4}'
$r.meta
```

확인할 항목:

| 필드 | 의미 |
|------|------|
| `fallback_used` | `true` → 재시도 소진 후 **fallback_answer** 노드에서 고정 문구 반환 (citation 비움) |
| `cannot_answer` | `true` → LLM이 “cannot answer” 문구를 생성했거나, fallback 사용 |
| `attempts_used` | 2면 재시도까지 한 뒤 실패한 것 |
| `eval_passed` | (아래 RAG_DEBUG 사용 시) rule-based 평가 통과 여부 |

- **citations가 비어 있고** `fallback_used == true` → **Judge/평가 실패**로 fallback 노드까지 간 경우.
- **citations가 있고** “cannot answer” + `Sources: [1][2][3][4]` → **synthesize 단계에서 LLM이 스스로 “답할 수 없다”고 한 경우** (아래 2번으로 원인 추적).

---

## 2. RAG_DEBUG로 context 확인

LLM에 실제로 어떤 context가 넘어갔는지 보려면 디버그 메타를 켭니다.  
**기본 설정(LangGraph 사용)이면 아래대로 하면 됩니다.** `meta.debug`는 LangGraph 파이프라인으로 답할 때만 응답에 붙습니다. (`RAG_USE_LANGGRAPH=false`로 서비스를 쓰면 `meta.debug`는 없음.)

**`.env` 에 추가:**

```env
RAG_DEBUG=true
```

서버 재시작 후 같은 요청을 다시 보냅니다.

```powershell
$r = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/rag/answer" `
  -Headers @{ Authorization="Bearer $env:ID_TOKEN" } `
  -ContentType "application/json" `
  -Body '{"query":"Summarize the document in 5 bullets","top_k":4}'
$r.meta.debug
```

`meta.debug` 에 다음이 포함됩니다.

- **`context_preview`**: LLM에 전달된 context 앞부분(최대 800자).  
  - 비어 있거나 문서 내용과 무관하면 **retrieval/필터 문제** 가능.
- **`context_length`**: context 전체 길이. 0이면 chunk가 하나도 안 넘어간 것.
- **`num_included_chunks`**: context에 포함된 chunk 개수. 0이면 검색 결과가 없거나 모두 걸러진 것.
- **`eval_passed`** / **`eval_reasons`**: rule-based 평가 통과 여부와 실패 이유.

여기서 **context가 비어 있거나**, **질문과 전혀 다른 내용**이면 retrieval(embedding/쿼리/필터)을 의심하면 됩니다.

---

## 3. 서버 로그 확인

Orchestrator를 실행한 터미널에서 다음 로그를 봅니다.

- `build_context retrieved=... included=...`  
  - `included` 가 0이면 chunk가 context에 하나도 안 들어간 것.
- `synthesize` 이벤트  
  - synthesize 단계까지 왔는지 확인.
- `fallback` 이벤트  
  - fallback 노드까지 갔다는 뜻 (재시도 소진 또는 정책상 fallback).

---

## 4. 자주 하는 조정

- **top_k 늘리기**  
  - `"top_k": 4` → `8` 또는 `12` 로 올려서 더 많은 chunk를 LLM에 넘겨 보기.
- **질문 바꿔 보기**  
  - “Summarize the document in 5 bullets” 대신  
    - “What are the main points in the document?”  
    - “List the key topics.”  
  - 같은 문서에 대해 답이 나오는지 보면, **질의와 retrieval/모델 해석** 문제 구분에 도움.
- **Judge 끄기 (평가 단계 제거)**  
  - Judge가 답을 기각해서 fallback으로 가는지 확인하려면:
  - `.env` 에 `JUDGE_ENABLED=false` 설정 후 재시작.  
  - 이렇게 하면 rule/judge 실패 경로 없이 **synthesize 결과만** 나옵니다.  
  - 여전히 “cannot answer”면 **모델이 context만 보고 거절**한 것이고,  
  - “cannot answer”가 사라지면 **Judge/평가 쪽**을 더 보면 됩니다.

---

## 5. 체크리스트

1. [ ] `meta.fallback_used`, `meta.cannot_answer`, `meta.attempts_used` 확인  
2. [ ] `RAG_DEBUG=true` 로 `meta.debug` 에서 `context_preview`, `num_included_chunks` 확인  
3. [ ] 서버 로그에서 `build_context` / `synthesize` / `fallback` 확인  
4. [ ] `top_k` 증가 및 질문 변경으로 재현  
5. [ ] `JUDGE_ENABLED=false` 로 Judge 경로 제거 후 동작 비교  

디버깅이 끝나면 `.env` 에서 `RAG_DEBUG` 를 제거하거나 `false` 로 두는 것을 권장합니다.
