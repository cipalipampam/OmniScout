
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.schemas.scrape_schema import (
    ScrapeJobResponse,
    ScrapeJobStatusResponse,
    ScrapeRunRequest,
)
from app.services.pipeline_service import pipeline_service

router = APIRouter(prefix="/pipeline", tags=["Social Media Scraping"])


# Endpoints

@router.post(
    "/run",
    response_model=ScrapeJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Jalankan Scraping (Background Job)",
    description=(
        "Menjalankan pengumpulan data secara lengkap dan otomatis: "
        "Scrape -> Filter/Deduplicate -> Normalize (opsional) -> Export CSV. "
        "Response langsung dikembalikan (202 Accepted) berisi job_id. "
        "Gunakan GET /api/v1/pipeline/status/{job_id} untuk memantau progress."
    ),
)
async def run_pipeline(req: ScrapeRunRequest) -> ScrapeJobResponse:
    """Buat dan jalankan pipeline end-to-end via PipelineService."""
    return await pipeline_service.create_and_start_pipeline_job(req)


@router.get(
    "/status/{job_id}",
    response_model=ScrapeJobStatusResponse,
    summary="Status Job Scraping",
    description=(
        "Polling status pipeline job berdasarkan job_id. "
        "Saat status='success', field statistics berisi ringkasan lengkap hasil scraping "
        "dan exported_file berisi nama file CSV yang bisa didownload."
    ),
)
def get_pipeline_status(job_id: str) -> ScrapeJobStatusResponse:
    """Kembalikan status dan hasil pipeline job dari PipelineService."""
    job_status = pipeline_service.get_job_status(job_id)
    if job_status is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline job dengan ID '{job_id}' tidak ditemukan.",
        )

    return job_status


@router.get(
    "/exports/{filename}",
    summary="Download File Hasil Scraping",
    description=(
        "Mendownload satu file CSV hasil analisis dari direktori storage/exports/. "
        "Dilindungi dengan validasi Path Traversal (is_relative_to)."
    ),
    response_class=FileResponse,
)
def download_export(filename: str) -> FileResponse:
    """Download file CSV hasil analisis dengan proteksi path traversal."""
    safe_path = pipeline_service.get_safe_export_path(filename)
    if safe_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File '{filename}' tidak valid atau tidak ditemukan di storage/exports/.",
        )

    return FileResponse(
        path=str(safe_path),
        media_type="text/csv",
        filename=filename,
    )
