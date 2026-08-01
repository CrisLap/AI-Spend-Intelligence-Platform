from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

_executor: ThreadPoolExecutor | None = None


def get_executor(max_workers: int = 4) -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="spendintel")
    return _executor


async def run_cpu_bound(fn, *args, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(get_executor(), fn, *args, **kwargs)
