# DB 구조 ↔ ROADMAP_USAGE_AND_CLOUD.md 일치 검토

**기준:** 실제 DB 컬럼 덤프 → `orchestrator/docs/db_schema_dump.json`  
(덤프는 `information_schema.columns` 형태의 table_name, column_name, data_type, is_nullable)

---

## 1. 로드맵과의 일치 여부

### Session 1 (문서 범위 지정)

| 로드맵 내용 | 덤프 기준 실제 DB | 일치 |
|-------------|-------------------|------|
| 문서 1개 = `sources.id` (source_id) | `sources.id` uuid PK 있음 | ✅ |
| chunk 소속 = `chunks.source_id` | `chunks.source_id` uuid NOT NULL 있음 | ✅ |
| retrieval 시 `WHERE user_id AND (optionally) source_id` | `sources.user_id`, `chunks`↔`sources` JOIN 가능. `s.id` 필터 추가 가능 | ✅ |

**결론:** Session 1에 필요한 DB 변경은 **없음**. API에서 `document_id`(= source_id) 받아서 `search_similar_chunks`에 넘기고, SQL에 `AND s.id = %s` 추가하면 됨.

### Session 3 (Active document / 질문 히스토리)

- **Active document:** 로드맵은 "user profile에 active_document_id 저장" 옵션을 둠. 덤프 기준 `users`에는 해당 컬럼 없음 → 필요 시 아래 (A) SQL로 추가.
- **질문 히스토리 per document:** 덤프에 **`rag_runs` / `rag_events` 테이블 없음**. RAG 로깅은 앱에서 선택 사항이므로 없어도 동작함. 나중에 `rag_runs`를 만들 때 `source_id` 컬럼을 넣으면 문서별 구분 가능 → 아래 (C) 참고.

---

## 2. 실제 DB(덤프) vs repo `sql/` 차이 요약

| 항목 | 덤프(실제) | repo sql/ | 비고 |
|------|------------|-----------|------|
| **chunks** | `created_at` 있음 | 10_schema에 없음 | 추가 컬럼만 있음, 무해 |
| **embeddings** | `id`(uuid PK), `chunk_id`, `embedding` | `chunk_id` PK, `embedding` | 앱은 `ON CONFLICT (chunk_id)` 사용 → **chunk_id가 UNIQUE여야 함**. PK가 id면 `chunk_id`에 UNIQUE 제약 필요. 아래 (D) 참고. |
| **jobs** | 동일 구조 | 50_schema_jobs와 일치 | ✅ |
| **notes** | 테이블 존재 (user_id, source_id, chunk_id, topic, content, created_at) | repo에 없음 | 앱 외부/다른 기능용으로 보임, 로드맵과 충돌 없음 |
| **sources** | `authors`, `published_at`, `hash` 없음 | 10_schema에 있음 | 현재 앱 코드에서 미사용. 필요 시 (E)로 추가 가능 |
| **summaries** | `topic`, `version` 있음 | 10_schema에는 없음 | 추가 컬럼만 있음, 무해 |
| **users** | `email`, `display_name` 없음 | 10_schema에 있음 | 현재 앱 코드에서 미사용. 필요 시 (E)로 추가 가능 |
| **rag_runs / rag_events** | 덤프에 없음 | 20_schema_rag_logs에 있음 | 선택 기능. 쓰려면 (C)로 생성 가능 |

---

## 3. SQL Editor에 넣을 수 있는 명령

아래는 **선택 사항**만 정리. Session 1 구현에는 **아무 SQL도 필수 아님**.

### (A) 사용자별 “현재 문서” 저장 (Active document, Session 3용)

```sql
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS active_source_id uuid REFERENCES sources(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_users_active_source_id
  ON users(active_source_id) WHERE active_source_id IS NOT NULL;

COMMENT ON COLUMN users.active_source_id IS 'Optional: last/active document for RAG when document_id not sent';
```

### (B) RAG 질의 문서 범위 기록 (rag_runs가 이미 있을 때만)

`rag_runs` 테이블이 **이미 있는 경우**에만 실행. 없으면 (C)에서 한 번에 생성.

```sql
ALTER TABLE rag_runs
  ADD COLUMN IF NOT EXISTS source_id uuid REFERENCES sources(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_rag_runs_source_id ON rag_runs(source_id);

COMMENT ON COLUMN rag_runs.source_id IS 'Optional: document (source) scoped for this RAG query when document_id was provided';
```

### (C) RAG 로깅 테이블이 없을 때 생성 (선택, source_id 포함)

`rag_runs` / `rag_events`가 아직 없을 때, 문서 범위까지 남기려면 아래로 생성.

```sql
CREATE TABLE IF NOT EXISTS rag_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  query text NOT NULL,
  top_k int NOT NULL,
  topic text,
  lang text,
  source_id uuid REFERENCES sources(id) ON DELETE SET NULL,
  status text NOT NULL DEFAULT 'running',
  latency_ms int,
  error_message text,
  created_at timestamptz DEFAULT now(),
  completed_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_rag_runs_user_id ON rag_runs(user_id);
CREATE INDEX IF NOT EXISTS idx_rag_runs_status ON rag_runs(status);
CREATE INDEX IF NOT EXISTS idx_rag_runs_created_at ON rag_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_rag_runs_source_id ON rag_runs(source_id);

CREATE TABLE IF NOT EXISTS rag_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id uuid NOT NULL REFERENCES rag_runs(id) ON DELETE CASCADE,
  event_type text NOT NULL,
  data jsonb,
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rag_events_run_id ON rag_events(run_id);
```

### (D) embeddings: chunk_id UNIQUE 확보 (ON CONFLICT 사용을 위해)

앱은 `INSERT INTO embeddings (chunk_id, embedding) ... ON CONFLICT (chunk_id) DO UPDATE` 를 사용합니다.  
덤프상 `embeddings`에 `id` PK와 `chunk_id`가 있으므로, **chunk_id가 UNIQUE가 아니면** 아래로 제약을 추가하세요.

```sql
-- chunk_id가 이미 UNIQUE/PK가 아니면 실행 (이미 있으면 에러 무시)
CREATE UNIQUE INDEX IF NOT EXISTS idx_embeddings_chunk_id_unique ON embeddings (chunk_id);
```

(PostgreSQL에서 UNIQUE INDEX가 있으면 ON CONFLICT (chunk_id) 사용 가능.)

### (E) repo와 컬럼 완전 동기화 (선택, 현재 앱 미사용)

나중에 repo 스키마와 맞추고 싶을 때만.

```sql
-- sources (현재 앱 코드에서 미사용)
ALTER TABLE sources ADD COLUMN IF NOT EXISTS authors text[];
ALTER TABLE sources ADD COLUMN IF NOT EXISTS published_at timestamptz;
ALTER TABLE sources ADD COLUMN IF NOT EXISTS hash text UNIQUE;

-- users (현재 앱 코드에서 미사용)
ALTER TABLE users ADD COLUMN IF NOT EXISTS email text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name text;
```

---

## 4. 요약

- **로드맵과 현재 덤프는 일치.** Session 1의 document_id(= source_id) 필터는 **DB 수정 없이** 앱만 수정하면 됨.
- **덤프는** `orchestrator/docs/db_schema_dump.json` 에 저장해 두었음.
- **(A)** Active document 쓰려면 실행 권장.
- **(B)** 이미 `rag_runs`가 있을 때 문서별 기록용.
- **(C)** RAG 로깅 테이블이 없을 때 한 번에 만들 때 사용 (source_id 포함).
- **(D)** embeddings에 `chunk_id` UNIQUE가 없으면 실행.
- **(E)** repo와 스키마 완전 동기화할 때만 선택.
