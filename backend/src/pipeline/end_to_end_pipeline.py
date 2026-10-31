
import asyncio
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd  

from configs.config import EXPORTS_DIR
from src.auth.session_manager import is_session_valid
from src.scraping.x_scraper import run_x_scraper, XScrapeConfig
from src.scraping.threads_scraper import run_threads_scraper, ThreadsScrapeConfig
from src.preprocessing.pipeline import PreprocessingPipeline

logger = logging.getLogger(__name__)



def _create_filename_slug(keywords: List[str] = None, platform: str = "both") -> str:
    """Membuat nama file unik berbasis timestamp dan keyword."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if keywords:
        raw_kw = "_".join(keywords[:2])
        clean_kw = re.sub(r"[^\w\-]", "_", raw_kw)[:25].strip("_")
        return f"analysis_{platform}_{clean_kw}_{ts}"
    return f"analysis_{platform}_{ts}"


def validate_platform_sessions(platform: str) -> Tuple[bool, List[str]]:
    """Satu-satunya sumber kebijakan validasi sesi per platform ('x' / 'threads' / 'both').

    Kembalikan (valid, errors); pesan error menyebut endpoint `login-trigger` karena tampil di UI.
    """
    plat = platform.lower().strip()
    errors: List[str] = []

    if plat in ("x", "both"):
        if not is_session_valid("x").get("is_valid", False):
            errors.append(
                "Sesi X (Twitter) tidak aktif. Login terlebih dahulu via "
                "POST /api/v1/auth/login-trigger/x"
            )

    if plat in ("threads", "both"):
        if not is_session_valid("threads").get("is_valid", False):
            errors.append(
                "Sesi Threads tidak aktif. Login terlebih dahulu via "
                "POST /api/v1/auth/login-trigger/threads"
            )

    return len(errors) == 0, errors


# Kelas EndToEndPipeline

class EndToEndPipeline:
    """Orchestrator scraping, optional normalization, statistics, and export."""

    def __init__(self):
        self.prep_pipeline = PreprocessingPipeline()
        self.scraping_errors: List[str] = []

    def _record_scraping_error(self, platform_label: str, error: Exception) -> None:
        """Catat kegagalan scraping satu platform beserta alasannya."""
        reason = getattr(error, "reason", None) or str(error)
        detail = getattr(error, "detail", "") or ""
        message = f"Scraping {platform_label} gagal: {reason}"
        if detail:
            message = f"{message}\n{detail}"
        self.scraping_errors.append(message)
        logger.error(message)

    def validate_sessions(self, platform: str) -> Dict[str, Any]:
        """Delegasi ke validate_platform_sessions(); kembalikan {"valid": bool, "errors": list[str]}."""
        valid, errors = validate_platform_sessions(platform)
        return {"valid": valid, "errors": errors}


    async def execute_scraping(
        self,
        keywords: Optional[List[str]] = None,
        direct_urls: Optional[List[str]] = None,
        platform: str = "both",
        search_mode: str = "latest",
        max_links: int = 100,
        max_scroll_steps: int = 500,
        headless: bool = False,
        status_callback: Optional[Callable[[str], None]] = None,
    ) -> pd.DataFrame:
        """Jalankan scraper sesuai platform; kembalikan DataFrame mentah gabungan yang sudah dideduplikasi."""
        platform = platform.lower().strip()
        frames = []
        self.scraping_errors = []

        if status_callback:
            status_callback(f"Memulai scraping pada platform [{platform.upper()}] dengan mode '{search_mode}'...")

        x_config = XScrapeConfig(
            search_mode=search_mode,
            max_links=max_links,
            search_scroll=max_scroll_steps,
            headless=headless,
        )
        threads_config = ThreadsScrapeConfig(
            search_mode=search_mode,
            max_links=max_links,
            search_scroll=max_scroll_steps,
            headless=headless,
        )

        if platform == "both":
            if status_callback:
                status_callback("Meluncurkan scraping paralel: X & Threads...")

            task_x = run_x_scraper(keywords=keywords, direct_urls=direct_urls, config=x_config, status_callback=status_callback)
            task_t = run_threads_scraper(keywords=keywords, direct_urls=direct_urls, config=threads_config, status_callback=status_callback)
            res_x, res_t = await asyncio.gather(task_x, task_t, return_exceptions=True)

            if isinstance(res_x, Exception):
                self._record_scraping_error("X", res_x)
            elif isinstance(res_x, pd.DataFrame) and not res_x.empty:
                frames.append(res_x)

            if isinstance(res_t, Exception):
                self._record_scraping_error("Threads", res_t)
            elif isinstance(res_t, pd.DataFrame) and not res_t.empty:
                frames.append(res_t)

        elif platform == "x":
            if status_callback:
                status_callback("Meluncurkan scraping X (Twitter)...")
            try:
                res_x = await run_x_scraper(keywords=keywords, direct_urls=direct_urls, config=x_config, status_callback=status_callback)
                if isinstance(res_x, pd.DataFrame) and not res_x.empty:
                    frames.append(res_x)
            except Exception as error:
                self._record_scraping_error("X", error)

        elif platform == "threads":
            if status_callback:
                status_callback("Meluncurkan scraping Threads...")
            try:
                res_t = await run_threads_scraper(keywords=keywords, direct_urls=direct_urls, config=threads_config, status_callback=status_callback)
                if isinstance(res_t, pd.DataFrame) and not res_t.empty:
                    frames.append(res_t)
            except Exception as error:
                # Termasuk ThreadsScrapeAborted (sesi tidak aktif / semua URL di-skip).
                self._record_scraping_error("Threads", error)

        if not frames:
            return pd.DataFrame(columns=["platform", "source", "user_id", "type", "date", "content"])

        df_merged = pd.concat(frames, ignore_index=True)
        # Deduplikasi berdasarkan source + content
        if "content" in df_merged.columns and "source" in df_merged.columns:
            df_merged = df_merged.drop_duplicates(subset=["source", "content"]).reset_index(drop=True)

        return df_merged


    def execute_preprocessing(
        self,
        df: pd.DataFrame,
        status_callback: Optional[Callable[[str], None]] = None,
    ) -> pd.DataFrame:
        """Wajib deduplicate dan merapikan whitespace pada ``content``."""
        if df.empty:
            return df

        if status_callback:
            status_callback(f"Menjalankan preprocessing wajib pada {len(df):,} data teks...")

        df_clean = self.prep_pipeline.transform_dataframe(
            df,
            text_column="content",
            show_progress=True,
        )
        return df_clean


    def compute_statistics(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Hitung ringkasan data scraping."""
        if df.empty:
            return {
                "total_data": 0,
                "platform_breakdown": {},
                "type_breakdown": {},
                "unique_users": 0,
                "unique_sources": 0,
            }

        total = len(df)
        plat_counts = df.get("platform", pd.Series(dtype=str)).value_counts().to_dict()
        plat_breakdown = {}
        for p, cnt in plat_counts.items():
            sub_df = df[df["platform"] == p]
            plat_breakdown[p] = {
                "total": int(cnt),
                "unique_users": int(sub_df["user_id"].nunique()) if "user_id" in sub_df else 0,
                "original_posts": int((sub_df["type"] == "Original Post").sum()) if "type" in sub_df else 0,
                "comments": int((sub_df["type"] != "Original Post").sum()) if "type" in sub_df else 0,
            }

        return {
            "total_data": total,
            "platform_breakdown": plat_breakdown,
            "type_breakdown": df.get("type", pd.Series(dtype=str)).value_counts().to_dict(),
            "unique_users": int(df["user_id"].nunique()) if "user_id" in df else 0,
            "unique_sources": int(df["source"].nunique()) if "source" in df else 0,
        }


    def export_results(
        self,
        df: pd.DataFrame,
        filename: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        platform: str = "both",
    ) -> Path:
        """Simpan DataFrame hasil analisis ke CSV (utf-8-sig) di storage/exports/."""
        if filename is None:
            filename = f"{_create_filename_slug(keywords, platform)}.csv"
        elif not filename.endswith(".csv"):
            filename = f"{filename}.csv"

        out_path = EXPORTS_DIR / filename
        df.to_csv(out_path, index=False, encoding="utf-8-sig")
        logger.info(f"Hasil analisis berhasil diekspor ke: {out_path}")
        return out_path


    async def run(
        self,
        keywords: Optional[List[str]] = None,
        direct_urls: Optional[List[str]] = None,
        platform: str = "both",
        search_mode: str = "latest",
        max_links: int = 50,
        max_scroll_steps: int = 300,
        headless: bool = False,
        export_csv: bool = True,
        output_filename: Optional[str] = None,
        status_callback: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """Jalankan seluruh alur end-to-end; kembalikan dict status + statistik + path ekspor."""
        t_start = datetime.now()

        # 1. Validasi Sesi
        if status_callback:
            status_callback("[Langkah 1/5] Memeriksa validitas sesi media sosial...")
        auth_check = self.validate_sessions(platform)
        if not auth_check["valid"]:
            return {
                "status": "error",
                "stage": "auth_validation",
                "message": "Sesi media sosial tidak valid.",
                "errors": auth_check["errors"],
            }

        # 2. Scraping
        if status_callback:
            status_callback(f"[Langkah 2/5] Memulai scraping data media sosial ({platform.upper()})...")
        df_raw = await self.execute_scraping(
            keywords=keywords,
            direct_urls=direct_urls,
            platform=platform,
            search_mode=search_mode,
            max_links=max_links,
            max_scroll_steps=max_scroll_steps,
            headless=headless,
            status_callback=status_callback,
        )

        if df_raw.empty:
            # Bedakan "memang tidak ada hasil" dari "scraping gagal" agar bug tidak
            # terlihat sebagai sukses tanpa data.
            if self.scraping_errors:
                first_line = self.scraping_errors[0].splitlines()[0]
                return {
                    "status": "error",
                    "stage": "scraping",
                    "message": first_line,
                    "errors": self.scraping_errors,
                    "total_data": 0,
                }
            return {
                "status": "warning",
                "stage": "scraping",
                "message": "Tidak ada data postingan yang berhasil dikumpulkan dari media sosial.",
                "total_data": 0,
            }

        # 3. Wajib preprocessing untuk deduplikasi dan konsistensi whitespace.
        if status_callback:
            status_callback(f"[Langkah 3/5] Membersihkan dan menormalisasi teks ({len(df_raw)} baris)...")
        df_clean = await asyncio.to_thread(
            self.execute_preprocessing,
            df_raw,
            status_callback,
        )

        # 4. Compute collection statistics.
        if status_callback:
            status_callback("[Langkah 4/5] Menghitung statistik data scraping...")
        df_scraped = df_clean

        # 5. Statistik & Ekspor
        if status_callback:
            status_callback("[Langkah 5/5] Menyiapkan rekapitulasi & mengekspor data...")
        stats = self.compute_statistics(df_scraped)

        exported_path = None
        if export_csv:
            exported_path = self.export_results(
                df_scraped,
                filename=output_filename,
                keywords=keywords,
                platform=platform,
            )

        t_elapsed = (datetime.now() - t_start).total_seconds()

        return {
            "status": "success",
            "platform": platform,
            "keywords": keywords or [],
            "direct_urls": direct_urls or [],
            "search_mode": search_mode,
            "total_data": len(df_scraped),
            "statistics": stats,
            "exported_file": str(exported_path) if exported_path else None,
            "elapsed_seconds": round(t_elapsed, 2),
            "dataframe": df_scraped,
        }



async def run_end_to_end_pipeline(
    keywords: Optional[List[str]] = None,
    direct_urls: Optional[List[str]] = None,
    platform: str = "both",
    search_mode: str = "latest",
    max_links: int = 50,
    max_scroll_steps: int = 300,
    headless: bool = False,
    export_csv: bool = True,
    output_filename: Optional[str] = None,
    status_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Pembungkus async: buat EndToEndPipeline lalu jalankan run()."""
    pipeline = EndToEndPipeline()
    return await pipeline.run(
        keywords=keywords,
        direct_urls=direct_urls,
        platform=platform,
        search_mode=search_mode,
        max_links=max_links,
        max_scroll_steps=max_scroll_steps,
        headless=headless,
        export_csv=export_csv,
        output_filename=output_filename,
        status_callback=status_callback,
    )


def run_pipeline_sync(
    keywords: Optional[List[str]] = None,
    direct_urls: Optional[List[str]] = None,
    platform: str = "both",
    search_mode: str = "latest",
    max_links: int = 50,
    max_scroll_steps: int = 300,
    headless: bool = False,
    export_csv: bool = True,
    output_filename: Optional[str] = None,
    status_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Pembungkus sinkron untuk CLI: asyncio.run(run_end_to_end_pipeline(...))."""
    return asyncio.run(
        run_end_to_end_pipeline(
            keywords=keywords,
            direct_urls=direct_urls,
            platform=platform,
            search_mode=search_mode,
            max_links=max_links,
            max_scroll_steps=max_scroll_steps,
            headless=headless,
            export_csv=export_csv,
            output_filename=output_filename,
            status_callback=status_callback,
        )
    )
