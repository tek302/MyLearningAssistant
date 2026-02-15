import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import load_env
from app.db.pool import close_pool, init_pool
from app.routers import documents, graph_test, ingest, ingest_status, rag

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage pool lifecycle and in-process job runner (Week6)."""
    import asyncio
    from app.worker.job_runner import run_forever

    dotenv_path = load_env()
    logger.info("Loaded .env from %s (override=false)", dotenv_path)
    await asyncio.to_thread(init_pool)
    task = asyncio.create_task(run_forever())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await asyncio.to_thread(close_pool)


app = FastAPI(title="Learning Agent Orchestrator", lifespan=lifespan)

# Include routers
app.include_router(graph_test.router)
app.include_router(ingest.router)
app.include_router(ingest_status.router)
app.include_router(rag.router)
app.include_router(documents.router)


@app.get("/health")
async def health():
    return {"status": "healthy"}

