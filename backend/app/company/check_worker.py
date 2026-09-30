"""Container health check using durable worker heartbeat, no credentials in output."""

import asyncio
import sys
from datetime import timedelta

from app.company.auth import aware
from app.db.session import SessionLocal
from app.models.company import WorkerHeartbeat
from app.models.operations import now


async def check():
    async with SessionLocal() as db:
        row = await db.get(WorkerHeartbeat, sys.argv[1])
        if not row or aware(row.updated_at) < now() - timedelta(seconds=90):
            raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(check())
