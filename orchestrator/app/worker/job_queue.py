"""
Week6: In-process job queue for async ingest (Option B).
Module-level asyncio queue of job_id (str); enqueue/dequeue only.
"""
import asyncio

_queue: asyncio.Queue[str] = asyncio.Queue()


async def enqueue(job_id: str) -> None:
    """Add job_id to the queue."""
    await _queue.put(job_id)


async def dequeue() -> str:
    """Wait and return next job_id."""
    return await _queue.get()
