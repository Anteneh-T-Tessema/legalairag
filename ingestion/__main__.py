"""Entry point for running the ingestion worker as a module: python -m ingestion.pipeline.worker"""

from __future__ import annotations

import asyncio

from ingestion.pipeline.worker import IngestionWorker


async def main() -> None:
    worker = IngestionWorker()
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
