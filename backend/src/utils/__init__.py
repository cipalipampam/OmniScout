"""
src.utils — Utilitas lintas-platform untuk runtime asyncio.

Export publik:
  ensure_proactor_loop  – Paksa Windows untuk menggunakan ProactorEventLoop
                          (diperlukan agar asyncio.subprocess & Playwright berjalan
                          di Windows dengan Python ≥ 3.8).
"""

from .async_compat import ensure_proactor_loop

__all__ = ["ensure_proactor_loop"]

