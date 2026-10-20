
from typing import Literal, Optional

from pydantic import BaseModel, Field


class SessionStatusItem(BaseModel):
    """Status sesi satu platform media sosial."""

    platform: str = Field(description="Nama platform (misal: 'X (Twitter)' atau 'Threads (Meta)').")
    is_valid: bool = Field(description="Status keabsahan sesi (True jika cookies/profil valid).")
    profile_path: str = Field(description="Nama folder profil sesi di storage.")
    message: str = Field(description="Keterangan kondisi status sesi.")


class LoginEnvironmentInfo(BaseModel):
    """Sumber kebenaran mode GUI login: 'novnc' (Docker) / 'native' (lokal) / 'unavailable'."""

    runtime: Literal["docker", "local"] = Field(
        description="Runtime backend: 'docker' (dalam container) atau 'local' (host langsung)."
    )
    gui_mode: Literal["novnc", "native", "unavailable"] = Field(
        description=(
            "'novnc' = GUI live di virtual display container (harus dipantau lewat noVNC); "
            "'native' = jendela browser muncul langsung di desktop user; "
            "'unavailable' = tidak ada display server, login interaktif tidak mungkin."
        )
    )
    novnc_url: Optional[str] = Field(
        default=None,
        description="URL viewer noVNC yang bisa dibuka user; hanya terisi saat gui_mode='novnc'.",
    )
    message: str = Field(description="Penjelasan kondisi GUI yang siap ditampilkan apa adanya di UI.")


class AllSessionsStatusResponse(BaseModel):
    """Status agregasi seluruh sesi (X dan Threads)."""

    x: SessionStatusItem = Field(description="Status sesi platform X.")
    threads: SessionStatusItem = Field(description="Status sesi platform Threads.")
    all_valid: bool = Field(description="True jika kedua sesi valid dan siap digunakan untuk scraping.")
    login_environment: LoginEnvironmentInfo = Field(
        description="Runtime & mode GUI yang akan dipakai saat login interaktif di-trigger."
    )


class LoginTriggerResponse(BaseModel):
    """Response saat trigger login interaktif berhasil diinisiasi di background."""

    platform: str = Field(description="Platform yang ditargetkan ('x' atau 'threads').")
    status: str = Field(description="Status inisiasi (misal: 'initiated').")
    message: str = Field(description="Petunjuk interaksi visual (noVNC bila runtime Docker, jendela desktop bila lokal).")

