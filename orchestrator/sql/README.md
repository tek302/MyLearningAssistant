# Database Schema Setup

이 디렉토리에는 Supabase 데이터베이스 스키마 SQL 파일이 포함되어 있습니다.

## 설치 순서

1. **Supabase 프로젝트 생성**
   - https://supabase.com 에서 새 프로젝트 생성
   - 프로젝트 설정에서 Database URL과 Service Role Key 확인

2. **SQL 파일 실행**
   Supabase Dashboard의 SQL Editor에서 다음 순서로 실행:

   ```sql
   -- 1. Extensions 활성화
   -- orchestrator/sql/00_enable_extensions.sql 파일 내용 실행
   
   -- 2. Core Schema 생성
   -- orchestrator/sql/10_schema_core.sql 파일 내용 실행
   
   -- 3. (선택사항) RAG 로그 스키마 생성
   -- orchestrator/sql/20_schema_rag_logs.sql 파일 내용 실행
   -- 이 테이블들은 선택사항이며, 없어도 RAG 기능은 정상 작동합니다 (애플리케이션 로깅으로 대체)
   
   -- 4. Jobs 테이블 (Week6 단일 프로세스 비동기 인제스트)
   -- orchestrator/sql/50_schema_jobs.sql 파일 내용 실행
   ```

   또는 Supabase CLI를 사용하는 경우:
   ```bash
   supabase db reset  # 개발 환경 초기화
   psql $DATABASE_URL -f sql/00_enable_extensions.sql
   psql $DATABASE_URL -f sql/10_schema_core.sql
   ```

3. **환경 변수 설정**
   `orchestrator/.env` 파일에 다음을 추가:
   ```
   SUPABASE_DB_URL=postgresql://postgres:[password]@db.[project-ref].supabase.co:5432/postgres
   ```

## 테이블 구조

- **users**: 사용자 정보 (Firebase UID 매핑)
- **sources**: 인제스트된 문서/URL 정보
- **chunks**: 문서의 텍스트 청크
- **embeddings**: 청크의 벡터 임베딩 (pgvector)
- **summaries**: S1/S2 요약 정보
- **rag_runs** (선택사항): RAG 쿼리 실행 로그
- **rag_events** (선택사항): RAG 이벤트 로그
- **jobs** (Week6): 비동기 인제스트 작업 (queued/running/done/failed)

## 주의사항

- `users` 테이블은 반드시 먼저 생성되어야 합니다 (다른 테이블이 참조)
- `vector` 확장은 pgvector를 사용하기 위해 필요합니다
- 프로덕션 환경에서는 RLS (Row Level Security) 정책을 설정해야 합니다

