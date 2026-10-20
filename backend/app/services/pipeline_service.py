import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from configs.config import EXPORTS_DIR
from src.pipeline.end_to_end_pipeline import EndToEndPipeline
from app.schemas.scrape_schema import (
    PlatformScrapeBreakdown,
    ScrapeJobResponse,
    ScrapeJobStatusResponse,
    ScrapeRunRequest,
    ScrapeStatistics,
)
from .job_service import job_manager

logger = logging.getLogger(__name__)


class PipelineService:
    """Service untuk background scraping dan penyajian berkas hasil."""

    async def create_and_start_pipeline_job(self, req: ScrapeRunRequest) -> ScrapeJobResponse:
        job_id = str(uuid.uuid4())
        job_manager.create_job(
            job_id=job_id,
            job_type="scrape",
            metadata={
                "platform": req.platform,
                "keywords": req.keywords,
                "search_mode": req.search_mode,
                "total_data": 0,
                "statistics": None,
                "exported_file": None,
            },
        )
        task = asyncio.create_task(self._execute_pipeline_worker(job_id, req))
        job_manager.track_task(task)
        return ScrapeJobResponse(
            job_id=job_id,
            status="queued",
            message=f"Scraping job berhasil diinisialisasi (ID: {job_id}).",
            platform=req.platform,
            keywords=req.keywords,
        )

    async def _execute_pipeline_worker(self, job_id: str, req: ScrapeRunRequest):
        started = datetime.now()
        async with job_manager.platform_lock(req.platform):
            job_manager.update_job(job_id, status="running", message="[Langkah 1/5] Memvalidasi sesi...")

            def on_status(message: str):
                job_manager.update_job(job_id, message=message)

            try:
                result = await EndToEndPipeline().run(
                    keywords=req.keywords,
                    direct_urls=req.direct_urls,
                    platform=req.platform,
                    search_mode=req.search_mode,
                    max_links=req.max_links,
                    max_scroll_steps=req.max_scroll_steps,
                    headless=req.headless,
                    export_csv=req.export_csv,
                    status_callback=on_status,
                )
                elapsed = round((datetime.now() - started).total_seconds(), 2)
                if result.get("status") in ("error", "warning"):
                    job_manager.update_job(
                        job_id,
                        status="error",
                        message=result.get("message", "Scraping gagal."),
                        elapsed_seconds=elapsed,
                        error_detail=str(result.get("errors", "")),
                    )
                    return

                exported_file = result.get("exported_file")
                job_manager.update_job(
                    job_id,
                    status="success",
                    message=f"Scraping selesai. {result.get('total_data', 0):,} data dikumpulkan.",
                    total_data=result.get("total_data", 0),
                    elapsed_seconds=elapsed,
                    statistics=self._build_statistics(result.get("statistics", {})),
                    exported_file=Path(exported_file).name if exported_file else None,
                    search_mode=req.search_mode,
                )
            except Exception as error:
                elapsed = round((datetime.now() - started).total_seconds(), 2)
                logger.error("Scraping job %s gagal: %s", job_id, error, exc_info=True)
                job_manager.update_job(
                    job_id,
                    status="error",
                    message="Scraping gagal karena terjadi error tidak terduga.",
                    elapsed_seconds=elapsed,
                    error_detail=str(error),
                )

    @staticmethod
    def _build_statistics(raw_stats: Any) -> ScrapeStatistics:
        raw: Dict[str, Any] = raw_stats if isinstance(raw_stats, dict) else {}
        platform_breakdown = {}
        for name, value in (raw.get("platform_breakdown") or {}).items():
            if isinstance(value, dict):
                platform_breakdown[str(name)] = PlatformScrapeBreakdown(
                    total=int(value.get("total") or 0),
                    unique_users=int(value.get("unique_users") or 0),
                    original_posts=int(value.get("original_posts") or 0),
                    comments=int(value.get("comments") or 0),
                )
        return ScrapeStatistics(
            total_data=int(raw.get("total_data") or 0),
            unique_users=int(raw.get("unique_users") or 0),
            unique_sources=int(raw.get("unique_sources") or 0),
            platform_breakdown=platform_breakdown,
            type_breakdown={
                str(name): int(value)
                for name, value in (raw.get("type_breakdown") or {}).items()
            },
        )

    @staticmethod
    def get_job_status(job_id: str) -> Optional[ScrapeJobStatusResponse]:
        job = job_manager.get_job(job_id)
        if job is None:
            return None
        return ScrapeJobStatusResponse(
            job_id=job_id,
            status=job["status"],
            message=job["message"],
            platform=job.get("platform"),
            keywords=job.get("keywords"),
            search_mode=job.get("search_mode"),
            total_data=job.get("total_data", 0),
            elapsed_seconds=job.get("elapsed_seconds"),
            statistics=job.get("statistics"),
            exported_file=job.get("exported_file"),
            error_detail=job.get("error_detail"),
        )

    @staticmethod
    def get_safe_export_path(filename: str) -> Optional[Path]:
        base_dir = Path(EXPORTS_DIR).resolve()
        target_path = (base_dir / filename).resolve()
        if not target_path.is_relative_to(base_dir):
            logger.warning("Percobaan path traversal terdeteksi: %s", filename)
            return None
        if not target_path.exists() or not target_path.is_file():
            return None
        return target_path


pipeline_service = PipelineService()
