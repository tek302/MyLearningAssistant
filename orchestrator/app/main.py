import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app.config import load_env
from app.db.pool import close_pool, init_pool
from app.routers import documents, graph_test, ingest, ingest_status, rag, worker
from app.utils.deps import get_user_id

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage pool lifecycle and Firebase Admin init. Job consumption is tick-driven via POST /worker/tick."""
    from app.utils.firebase_auth import init_firebase

    dotenv_path = load_env()
    logger.info("Loaded .env from %s (override=false)", dotenv_path)
    import asyncio
    await asyncio.to_thread(init_firebase)
    await asyncio.to_thread(init_pool)
    yield
    await asyncio.to_thread(close_pool)


app = FastAPI(title="Learning Agent Orchestrator", lifespan=lifespan)

# Include routers
app.include_router(graph_test.router)
app.include_router(ingest.router)
app.include_router(ingest_status.router)
app.include_router(rag.router)
app.include_router(documents.router)
app.include_router(worker.router)


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/me")
async def me(user_id: str = Depends(get_user_id)):
    """Return current user's firebase_uid (for token check / who-am-i)."""
    return {"firebase_uid": user_id}


@app.post("/me/trigger-worker")
async def trigger_worker(user_id: str = Depends(get_user_id)):
    """
    Trigger one worker tick (claim and process one queued job).
    Requires Bearer auth. For manual processing from the app.
    Returns { "status": "ok", "processed": true|false [, "job_id": "..." ] }.
    """
    from app.db.repo import SupabaseRepo
    from app.worker.job_runner import process_job

    repo = SupabaseRepo()
    job_id = repo.claim_one_queued_job()
    if job_id:
        logger.info("trigger_worker: user=%s claimed job_id=%s", user_id, job_id)
        await process_job(job_id)
        return {"status": "ok", "processed": True, "job_id": job_id}
    return {"status": "ok", "processed": False}

