
import logging
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Path, status

from app.schemas.auth_schema import (
    AllSessionsStatusResponse,
    LoginTriggerResponse,
)
from app.services.auth_service import auth_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Autentikasi & Sesi"])


# Endpoints

@router.get(
    "/status",
    response_model=AllSessionsStatusResponse,
    summary="Cek Status Semua Sesi Login",
    description=(
        "Memeriksa ketersediaan dan keabsahan sesi login browser persisten "
        "untuk platform X (Twitter) dan Threads. "
        "Menyertakan `login_environment` (runtime + mode GUI) agar frontend tahu "
        "apakah login interaktif muncul di noVNC (Docker) atau di desktop user (lokal). "
        "Tidak membuka browser; didelegasikan ke AuthService untuk memeriksa kondisi filesystem."
    ),
)
def get_session_status() -> AllSessionsStatusResponse:
    """Kembalikan status sesi X dan Threads + lingkungan GUI via AuthService."""
    return auth_service.get_all_sessions_status()


@router.post(
    "/login-trigger/{platform}",
    response_model=LoginTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger Login Interaktif (noVNC / Browser Native)",
    description=(
        "Memicu proses login interaktif Playwright GUI untuk platform tertentu. "
        "Proses berjalan di background via BackgroundTasks. "
        "Mode GUI mengikuti runtime: Docker menampilkan browser di noVNC, "
        "runtime lokal membuka browser langsung di desktop user."
    ),
)
async def trigger_login(
    background_tasks: BackgroundTasks,
    platform: Literal["x", "threads"] = Path(
        ...,
        description="Platform yang akan di-login: 'x' atau 'threads'.",
    ),
) -> LoginTriggerResponse:
    """Inisiasi background login task untuk platform yang dipilih."""
    platform_name = "X (Twitter)" if platform == "x" else "Threads (Meta)"
    env = auth_service.get_login_environment()

    if env.gui_mode == "unavailable":
        logger.warning(f"Login trigger gagal — display tidak tersedia: {env.message}")
        hint = "Coba restart container backend." if env.runtime == "docker" else (
            "Jalankan backend di host dengan desktop/GUI, atau set up virtual display."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Layanan GUI tidak tersedia untuk platform {platform_name}. "
                f"Detail: {env.message} {hint}"
            ),
        )

    # Delegasikan task worker ke AuthService
    background_tasks.add_task(auth_service.run_login_task, platform)

    if env.gui_mode == "novnc":
        msg = (
            f"Proses login {platform_name} sedang diinisiasi di background. "
            "Browser GUI berjalan pada virtual display container. "
            f"Buka {env.novnc_url} di browser Anda untuk melihat dan menyelesaikan login. "
            "Setelah selesai, cek status sesi di GET /api/v1/auth/status."
        )
    else:
        msg = (
            f"Proses login {platform_name} sedang diinisiasi di background. "
            "Jendela browser akan terbuka langsung di desktop perangkat ini — "
            "selesaikan login pada jendela tersebut. "
            "Setelah selesai, cek status sesi di GET /api/v1/auth/status."
        )

    logger.info(f"Login trigger diterima untuk platform: {platform} (mode GUI: {env.gui_mode})")

    return LoginTriggerResponse(
        platform=platform,
        status="initiated",
        message=msg,
    )
