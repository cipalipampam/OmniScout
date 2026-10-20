import asyncio
import logging
import sys
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.routers import auth_router, pipeline_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = FastAPI(
    title="Social Media Data Scraper API",
    description=(
        "REST API untuk mengumpulkan data publik dari X (Twitter) dan Threads (Meta).\n\n"
        "### Alur Kerja\n"
        "1. **Auth** — Pastikan sesi browser X & Threads aktif\n"
        "2. **Scrape** — Kumpulkan postingan berdasarkan keyword atau URL\n"
        "3. **Normalize (opsional)** — Bersihkan teks tanpa mengubah data mentah\n"
        "4. **Export** — Simpan hasil scraping ke CSV\n"
    ),
    version="2.0.0",
    contact={"name": "Social Media Data Scraper"},
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"
app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(pipeline_router, prefix=API_PREFIX)


@app.get(f"{API_PREFIX}/health", tags=["Health Check"], summary="Lightweight Health Check")
def health_check():
    return {"status": "ok", "online": True}


@app.get("/", tags=["Health Check"], summary="Health Check & Info Server")
def root():
    return {
        "status": "online",
        "service": "Social Media Data Scraper — FastAPI Backend",
        "version": "2.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "endpoints": {
            "auth": f"{API_PREFIX}/auth",
            "pipeline": f"{API_PREFIX}/pipeline",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main_api:app", host="0.0.0.0", port=8080, reload=True)
