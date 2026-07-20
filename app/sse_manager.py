"""Server-Sent Events (SSE) manager for real-time job status updates.

Maintains connections to clients and broadcasts job status changes
without latency. Enables instant synchronization across notification
list and job details modal.
"""

import asyncio
import json
import logging
from typing import Set, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class JobUpdate:
    """Job status update to broadcast to clients."""
    job_name: str
    status: str  # running, success, failed, etc.
    start_time: str
    end_time: str = None
    error_message: str = None
    retry_count: int = 0
    max_retries: int = 0


class SSEManager:
    """Manages SSE connections and broadcasts job updates."""

    def __init__(self):
        self.client_queues: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def add_client(self, queue: asyncio.Queue) -> None:
        """Register a new SSE client."""
        async with self._lock:
            self.client_queues.add(queue)
        logger.debug(f"SSE client connected. Total clients: {len(self.client_queues)}")

    async def remove_client(self, queue: asyncio.Queue) -> None:
        """Unregister an SSE client."""
        async with self._lock:
            self.client_queues.discard(queue)
        logger.debug(f"SSE client disconnected. Total clients: {len(self.client_queues)}")

    async def broadcast_update(self, update: JobUpdate) -> None:
        """Broadcast a job update to all connected clients."""
        if not self.client_queues:
            logger.debug("No SSE clients connected, skipping broadcast")
            return

        message = json.dumps({
            "job_name": update.job_name,
            "status": update.status,
            "start_time": update.start_time,
            "end_time": update.end_time,
            "error_message": update.error_message,
            "retry_count": update.retry_count,
            "max_retries": update.max_retries,
        })

        async with self._lock:
            queues_snapshot = list(self.client_queues)

        # Send to all clients concurrently
        for queue in queues_snapshot:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning(f"SSE queue full, dropping message for a client")
            except Exception as e:
                logger.error(f"Error broadcasting to SSE client: {e}")

        logger.debug(f"Broadcasted update to {len(queues_snapshot)} SSE clients")

    def get_client_count(self) -> int:
        """Return number of connected clients."""
        return len(self.client_queues)


# Global SSE manager instance
sse_manager = SSEManager()
