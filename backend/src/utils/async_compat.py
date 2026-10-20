
# Uvicorn `--reload` memaksa SelectorEventLoop, padahal Playwright butuh ProactorEventLoop
# untuk `create_subprocess_exec()` — tanpa helper ini muncul NotImplementedError.

import asyncio
import functools
import sys
from typing import Any, Callable, Coroutine


def ensure_proactor_loop(async_fn: Callable[..., Coroutine[Any, Any, Any]]) -> Callable[..., Coroutine[Any, Any, Any]]:
    """Jalankan fungsi async di thread ProactorEventLoop bila loop aktif hanyalah SelectorEventLoop."""
    @functools.wraps(async_fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        if sys.platform == "win32":
            current_loop = asyncio.get_running_loop()
            proactor_cls = getattr(asyncio, "ProactorEventLoop", None)

            # Jika loop aktif bukan ProactorEventLoop (contoh: SelectorEventLoop)
            if proactor_cls and not isinstance(current_loop, proactor_cls):
                def _run_in_proactor_thread():
                    new_loop = asyncio.ProactorEventLoop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(async_fn(*args, **kwargs))
                    finally:
                        try:
                            # Batalkan sisa pending task jika ada
                            pending = asyncio.all_tasks(new_loop)
                            for task in pending:
                                task.cancel()
                            if pending:
                                new_loop.run_until_complete(
                                    asyncio.gather(*pending, return_exceptions=True)
                                )
                            new_loop.close()
                        except Exception:
                            pass

                return await asyncio.to_thread(_run_in_proactor_thread)

        return await async_fn(*args, **kwargs)

    return wrapper
