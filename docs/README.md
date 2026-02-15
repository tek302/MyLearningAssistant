# Learning Agent - Orchestrator

## Running the Orchestrator Locally

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

### Setup

1. Navigate to the orchestrator directory:
   ```bash
   cd orchestrator
   ```

2. Create a virtual environment (recommended):
   ```bash
   python -m venv venv
   ```

3. Activate the virtual environment:
   - On Windows:
     ```bash
     venv\Scripts\activate
     ```
   - On macOS/Linux:
     ```bash
     source venv/bin/activate
     ```

4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

5. Set up environment variables:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` with your configuration values. Required variables:
   - `OPENAI_API_KEY` - Your OpenAI API key
   - `SUPABASE_URL` - Your Supabase project URL
   - `SUPABASE_SERVICE_ROLE_KEY` - Your Supabase service role key
   - `SUPABASE_DB_URL` - PostgreSQL connection URI
   - `FIREBASE_SERVICE_ACCOUNT_JSON` - Path to Firebase service account JSON file
   - `APP_ENV` - Application environment (default: local)
   - `LOG_LEVEL` - Logging level (default: INFO)

### Running the Server

Start the FastAPI server with uvicorn:

```bash
uvicorn app.main:app --reload
```

The server will start on `http://localhost:8000` by default.

### API Endpoints

#### Health Check

**GET** `/health`

Returns the health status of the server.

**Example request:**
```bash
curl http://localhost:8000/health
```

**Example response:**
```json
{
  "status": "healthy"
}
```

#### Echo Graph

**POST** `/graph/echo`

Runs the echo graph with user input. Requires authentication via Bearer token.

**Example request:**
```bash
curl -X POST http://localhost:8000/graph/echo \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_FIREBASE_ID_TOKEN" \
  -d '{"input": "Hello, world!"}'
```

**Example response:**
```json
{
  "output": "user_id: Hello, world!"
}
```

#### Ingest URL

**POST** `/ingest/url`

Fetches a URL, extracts text content, chunks it, computes embeddings, creates S1 summary, and persists to Supabase tables `sources`, `chunks`, `embeddings`, and `summaries`. Supports both HTML and PDF URLs. Requires authentication via Bearer token.

**Supported formats:**
- HTML pages (uses BeautifulSoup for text extraction)
- PDF documents (uses PyMuPDF, up to 100 pages by default, 25 MB size limit)

**Example request (HTML):**
```bash
curl -X POST http://localhost:8000/ingest/url \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_FIREBASE_ID_TOKEN" \
  -d '{"url": "https://example.com/article"}'
```

**Example request (PDF - arXiv):**
```bash
curl -X POST http://localhost:8000/ingest/url \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_FIREBASE_ID_TOKEN" \
  -d '{"url": "https://arxiv.org/pdf/2301.00001.pdf"}'
```

**Example response:**
```json
{
  "source_id": "550e8400-e29b-41d4-a716-446655440000",
  "url": "https://arxiv.org/pdf/2301.00001.pdf",
  "title": "",
  "chunk_count": 45,
  "embedding_count": 45,
  "summary_id": "660e8400-e29b-41d4-a716-446655440001",
  "tldr": "This paper presents a novel approach to machine learning with applications in natural language processing.",
  "bullets_count": 5,
  "content_type": "pdf",
  "pages_used": 12
}
```

**Configuration:**
- `MAX_PDF_PAGES`: Maximum pages to process from PDF (default: 100)
- `MAX_PDF_MB`: Maximum PDF file size in MB (default: 25)
- Minimum text length: 500 characters (returns 400 error if below)

---

## RAG (Retrieval-Augmented Generation)

**POST** `/rag/answer`

Answers user queries using RAG by retrieving relevant chunks from ingested sources via vector similarity search, then synthesizing an answer with citations using an LLM.

**Request body:**
```json
{
  "query": "What is FastAPI?",
  "top_k": 8,
  "topic": "web-frameworks",
  "lang": "en"
}
```

- `query` (required): User query string (1-1000 characters)
- `top_k` (optional): Number of chunks to retrieve (default: 8, max: 50)
- `topic` (optional): Filter by topic (checks `sources.meta->>'topic'`)
- `lang` (optional): Filter by language (checks `sources.lang`)

**Example request:**
```bash
curl -X POST http://localhost:8000/rag/answer \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_FIREBASE_ID_TOKEN" \
  -d '{
    "query": "What is FastAPI?",
    "top_k": 5
  }'
```

**Example response:**
```json
{
  "answer": "FastAPI is a modern web framework for building APIs with Python [1]. It is based on standard Python type hints [2] and provides automatic API documentation [3].",
  "citations": [
    {
      "chunk_id": "550e8400-e29b-41d4-a716-446655440000",
      "source_id": "660e8400-e29b-41d4-a716-446655440001",
      "url": "https://en.wikipedia.org/wiki/FastAPI",
      "title": "FastAPI - Wikipedia",
      "chunk_index": 1,
      "score": 0.85,
      "quote": "FastAPI is a modern web framework for building APIs with Python..."
    }
  ],
  "meta": {
    "top_k": 5,
    "latency_ms": 1234,
    "model": "gpt-4o-mini"
  }
}
```

**Response fields:**
- `answer`: Synthesized answer with citation markers [1], [2], etc.
- `citations`: Array of citation objects with chunk/source info and similarity scores
- `meta`: Metadata including `top_k`, `latency_ms`, and `model` used

**Configuration:**
- Uses same embedding model as ingest (`EMBEDDING_MODEL`, default: `text-embedding-3-small`)
- Uses same LLM model as S1 summaries (`SUMMARY_MODEL`, default: `gpt-4o-mini`)
- Context limits: max 8 chunks, max 12,000 characters total
- Citation quotes: max 240 characters

**Logging:**
- Optionally logs runs and events to `rag_runs` and `rag_events` tables if they exist
- Falls back to application logging if tables are not present
- See `orchestrator/sql/20_schema_rag_logs.sql` for optional schema

---

### Testing

The orchestrator includes an automated integration test suite using pytest.

#### Setup for Testing

1. **Activate your virtual environment:**
   ```bash
   # Windows
   venv\Scripts\activate
   
   # macOS/Linux
   source venv/bin/activate
   ```

2. **Install development dependencies:**
   ```bash
   pip install -r requirements-dev.txt
   ```

3. **Set up environment variables:**
   - Ensure `.env` file exists with `SUPABASE_DB_URL` set
   - Tests use `AUTH_BYPASS_USER_ID=dev-user` automatically (no Firebase required)
   - `OPENAI_API_KEY` must be set for embedding and summarization tests

#### Running Tests

Run all tests:
```bash
pytest -q
```

Run specific test file:
```bash
pytest tests/test_ingest_pdf.py -v
```

Run with verbose output:
```bash
pytest -v
```

#### Test Coverage

The test suite includes:
- **Health check**: `/health` endpoint
- **PDF ingest**: Full pipeline test with arXiv PDF
- **HTML ingest**: Long HTML page processing
- **Idempotency**: Verifies same URL can be ingested multiple times safely
- **RAG answer**: Query answering with citations and latency checks

Tests are deterministic and idempotent - safe to re-run multiple times.

### Development

The `--reload` flag enables auto-reload on code changes during development.

