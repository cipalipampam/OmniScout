
import logging
import os
import sys
from pathlib import Path

from configs.config import X_PROFILE_DIR, THREADS_PROFILE_DIR
from src.auth.login_threads import setup_threads_login
from src.auth.login_x import setup_x_login
from src.auth.session_manager import get_all_sessions_status
from app.schemas.auth_schema import (
    AllSessionsStatusResponse,
    LoginEnvironmentInfo,
    SessionStatusItem,
)

logger = logging.getLogger(__name__)


# Mode yang diakui untuk env `LOGIN_GUI_MODE`. Nilai ini di-set EKSPLISIT oleh
# docker-compose.yml ("novnc") supaya deteksi tidak bergantung pada tebakan.
VALID_GUI_MODES = ("novnc", "native", "unavailable")

# Sentinel runtime container (Docker membuat file ini di root filesystem).
DOCKER_SENTINEL = Path("/.dockerenv")

# Port default viewer noVNC (websockify) bila `NOVNC_PORT` tidak di-set.
DEFAULT_NOVNC_PORT = "6080"

NOVNC_VIEW_PATH = "/vnc.html"


class AuthService:
    """Service untuk urusan autentikasi dan status sesi scraper."""

    @staticmethod
    def get_login_environment() -> LoginEnvironmentInfo:
        """Tentukan di mana GUI login muncul: 'novnc' (Docker) / 'native' (desktop) / 'unavailable'.

        Urutan keputusan: env LOGIN_GUI_MODE → Windows = native → ada DISPLAY = novnc/native → unavailable.
        """
        forced_mode    = os.environ.get("LOGIN_GUI_MODE", "").strip().lower()
        is_container   = DOCKER_SENTINEL.exists() or os.environ.get("HATESENSE_RUNTIME", "").strip().lower() == "docker"
        display        = os.environ.get("DISPLAY", "").strip()
        wayland        = os.environ.get("WAYLAND_DISPLAY", "").strip()

        if forced_mode in VALID_GUI_MODES:
            gui_mode = forced_mode
        elif sys.platform == "win32":
            gui_mode = "native"
        elif display or wayland:
            gui_mode = "novnc" if is_container else "native"
        else:
            gui_mode = "unavailable"

        novnc_url = None
        if gui_mode == "novnc":
            port = os.environ.get("NOVNC_PORT", "").strip() or DEFAULT_NOVNC_PORT
            novnc_url = (
                os.environ.get("NOVNC_PUBLIC_URL", "").strip()
                or f"http://localhost:{port}{NOVNC_VIEW_PATH}"
            )

        messages = {
            "novnc": (
                "GUI browser berjalan pada virtual display container Docker. "
                f"Pantau dan selesaikan login melalui noVNC: {novnc_url}"
            ),
            "native": (
                "Jendela browser Playwright akan terbuka langsung di desktop perangkat ini. "
                "Selesaikan login pada jendela tersebut."
            ),
            "unavailable": (
                "Tidak ada display server yang terdeteksi ($DISPLAY / $WAYLAND_DISPLAY kosong). "
                "Login interaktif tidak dapat dibuka pada runtime ini."
            ),
        }

        return LoginEnvironmentInfo(
            runtime="docker" if is_container else "local",
            gui_mode=gui_mode,
            novnc_url=novnc_url,
            message=messages[gui_mode],
        )

    @staticmethod
    def get_all_sessions_status() -> AllSessionsStatusResponse:
        """Mengambil status keabsahan sesi login X dan Threads dari filesystem profil."""
        statuses = get_all_sessions_status()

        x_info = statuses.get("x", {})
        t_info = statuses.get("threads", {})

        x_item = SessionStatusItem(
            platform="X (Twitter)",
            is_valid=x_info.get("is_valid", False),
            profile_path=X_PROFILE_DIR.name,
            message=x_info.get("message", "Status tidak diketahui."),
        )
        t_item = SessionStatusItem(
            platform="Threads (Meta)",
            is_valid=t_info.get("is_valid", False),
            profile_path=THREADS_PROFILE_DIR.name,
            message=t_info.get("message", "Status tidak diketahui."),
        )

        return AllSessionsStatusResponse(
            x=x_item,
            threads=t_item,
            all_valid=x_item.is_valid and t_item.is_valid,
            login_environment=AuthService.get_login_environment(),
        )

    @staticmethod
    async def run_login_task(platform: str):
        """Menjalankan proses login interaktif Playwright di background."""
        from app.services.job_service import job_manager

        plat = platform.lower().strip()
        try:
            async with job_manager.platform_lock(plat):
                if plat == "x":
                    logger.info("AuthService: Memulai background login X...")
                    await setup_x_login(str(X_PROFILE_DIR))
                    logger.info("AuthService: Background login X selesai.")
                elif plat == "threads":
                    logger.info("AuthService: Memulai background login Threads...")
                    await setup_threads_login(str(THREADS_PROFILE_DIR))
                    logger.info("AuthService: Background login Threads selesai.")
                else:
                    logger.warning(f"AuthService: Platform tidak dikenal: {platform}")
        except Exception as e:
            logger.error(f"AuthService: Error saat login {platform}: {e}", exc_info=True)


# Singleton instance
auth_service = AuthService()

