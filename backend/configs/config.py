
from pathlib import Path
from dotenv import load_dotenv

# Muat environment variables dari .env bila tersedia
load_dotenv()

BACKEND_DIR = Path(__file__).resolve().parent.parent

STORAGE_DIR     = BACKEND_DIR / "storage"
SESSIONS_DIR    = STORAGE_DIR / "sessions"
EXPORTS_DIR     = STORAGE_DIR / "exports"
DICT_DIR        = STORAGE_DIR / "dictionaries"

X_PROFILE_DIR       = SESSIONS_DIR / "x_profile"
THREADS_PROFILE_DIR = SESSIONS_DIR / "threads_profile"

KAMUSALAY_PATH = DICT_DIR / "kamusalay.csv"

SCRAPER_CONFIG = {
    # CATATAN: tidak ada kunci "headless" di sini. Opsi itu dikendalikan per-request
    # (`ScrapeRunRequest.headless`, default dataclass scraper = True),
    # sedangkan proses login SELALU memakai GUI (`create_browser(..., headless=False)`).
    # Sebelumnya kunci `headless` ada di sini tetapi tidak pernah dibaca siapa pun (dead config).
    "search_mode"       : "latest",         # "latest" (Terbaru/Recent) atau "top" (Terpopuler/Default)
    "goto_timeout_ms"   : 60_000,           # Timeout navigasi halaman (ms)
    "delay_range"       : (2.0, 4.0),       # Range random delay antar aksi (detik)
    "max_links"         : 500,              # Batas maks URL postingan per keyword
    "search_scroll"     : 300,              # Batas default scroll discovery per keyword
    "scan_step_px"      : 250,             # Langkah scroll micro-step (px)
    "scan_delay_range"  : (0.15, 0.30),    # Delay antar langkah scroll (detik)
    "scan_max_steps"    : 3000,            # Batas pengaman langkah deep crawl per postingan
}

for _dir in (SESSIONS_DIR, EXPORTS_DIR, DICT_DIR, X_PROFILE_DIR, THREADS_PROFILE_DIR):
    _dir.mkdir(parents=True, exist_ok=True)
