
import asyncio
import logging
from collections import OrderedDict
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)


class JobManager:
    """Manajer state job asinkron terpusat: FIFO eviction, task guard, lock per platform."""

    def __init__(self, max_jobs: int = 150):
        self._max_jobs = max_jobs
        self._jobs: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._active_tasks: Set[asyncio.Task] = set()

        # Platform-specific async locks untuk akses browser Chromium persisten
        self._lock_x = asyncio.Lock()
        self._lock_threads = asyncio.Lock()


    def create_job(self, job_id: str, job_type: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Mendaftarkan job baru dengan status awal 'queued'."""
        self._evict_if_needed()

        job_record = {
            "job_id": job_id,
            "job_type": job_type,
            "status": "queued",
            "message": "Job dibuat dan menunggu antrean eksekusi.",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "elapsed_seconds": None,
            "error_detail": None,
            **metadata,
        }
        self._jobs[job_id] = job_record
        return job_record

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Mengambil data job berdasarkan job_id."""
        return self._jobs.get(job_id)

    def update_job(self, job_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Memperbarui field tertentu pada job record."""
        if job_id not in self._jobs:
            logger.warning(f"Percobaan memperbarui job yang tidak ada: {job_id}")
            return None

        self._jobs[job_id].update(kwargs)
        self._jobs[job_id]["updated_at"] = datetime.now().isoformat()
        return self._jobs[job_id]

    def _evict_if_needed(self):
        """Hapus job TERTUA YANG SUDAH SELESAI bila kapasitas terlampaui.

        Job 'queued'/'running' tidak pernah dibuang: menghapusnya membuat endpoint status
        membalas 404 sementara worker masih bekerja (frontend menandai analisis GAGAL).
        """
        if len(self._jobs) < self._max_jobs:
            return

        # Hanya job yang sudah selesai (success/error) yang boleh dibuang.
        finished_keys = [
            job_id
            for job_id, data in self._jobs.items()
            if data.get("status") in ("success", "error")
        ]

        if not finished_keys:
            logger.warning(
                f"JobManager: kapasitas {self._max_jobs} terlampaui oleh {len(self._jobs)} job "
                "yang masih aktif. Tidak ada job dibuang agar status polling tidak hilang."
            )
            return

        # Buang seperlunya saja: sisakan ruang untuk job baru yang sedang dibuat.
        overflow = len(self._jobs) - self._max_jobs + 1
        for job_id in finished_keys[:max(overflow, 1)]:
            self._jobs.pop(job_id, None)
            logger.debug(f"JobManager: Job {job_id} (sudah selesai) dihapus dari memori untuk menjaga kapasitas.")


    def track_task(self, task: asyncio.Task):
        """Simpan strong reference ke asyncio.Task agar tidak di-garbage collect di tengah eksekusi."""
        self._active_tasks.add(task)
        task.add_done_callback(self._active_tasks.discard)


    @asynccontextmanager
    async def platform_lock(self, platform: str):
        """Context manager lock per platform agar profil browser tidak dipakai bersamaan."""
        plat = platform.lower().strip()
        acquired_locks = []

        try:
            if plat in ("x", "both"):
                logger.info(f"Mengantre lock platform [X]...")
                await self._lock_x.acquire()
                acquired_locks.append(self._lock_x)
                logger.info(f"Lock platform [X] berhasil diperoleh.")

            if plat in ("threads", "both"):
                logger.info(f"Mengantre lock platform [THREADS]...")
                await self._lock_threads.acquire()
                acquired_locks.append(self._lock_threads)
                logger.info(f"Lock platform [THREADS] berhasil diperoleh.")

            yield

        finally:
            for lock in reversed(acquired_locks):
                if lock.locked():
                    lock.release()
            logger.info(f"Seluruh lock browser untuk platform [{plat}] telah dilepaskan.")


# Singleton instance terpusat
job_manager = JobManager()

