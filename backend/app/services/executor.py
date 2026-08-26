from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

_executor: ThreadPoolExecutor | None = None
_init_lock = threading.RLock()


def get_executor(max_workers: int = 4) -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        with _init_lock:
            if _executor is None:  # re-check inside the lock (double-checked locking)
                _executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="spendintel")
    return _executor


async def run_cpu_bound(fn, *args, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(get_executor(), fn, *args, **kwargs)
