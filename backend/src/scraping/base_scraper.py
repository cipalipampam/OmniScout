
import asyncio
import logging
import os
import random
from pathlib import Path

import pandas as pd

logger = logging.getLogger("base_scraper")


STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
    "--disable-extensions",
]

STEALTH_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en', 'id'] });
"""


# Browser Factory — Persistent Context

async def create_browser(playwright, profile_dir: str, headless: bool = False):
    """Buka browser persistent (Chrome → Edge → Chromium); kembalikan (context, page)."""
    for channel in ("chrome", "msedge", None):
        try:
            launch_kwargs = {"headless": headless, "args": STEALTH_ARGS}
            if channel:
                launch_kwargs["channel"] = channel

            context = await playwright.chromium.launch_persistent_context(
                profile_dir, **launch_kwargs
            )
            browser_name = channel or "Chromium (bundled)"
            logger.info(f"Browser terbuka: {browser_name} | Profile: {profile_dir}")

            page = context.pages[0] if context.pages else await context.new_page()
            await page.add_init_script(STEALTH_SCRIPT)
            return context, page

        except Exception as e:
            logger.debug(f"Gagal membuka {channel or 'chromium'}: {e}")
            continue

    raise RuntimeError(
        "Tidak dapat membuka browser. Pastikan Google Chrome atau Microsoft Edge "
        "terinstal di sistem Anda."
    )



async def random_delay(delay_range: tuple):
    """Tunda eksekusi dengan durasi acak (mitigasi deteksi bot)."""
    await asyncio.sleep(random.uniform(*delay_range))


# Penanganan Data & Penyimpanan

STANDARD_SCRAPER_COLUMNS = ["platform", "source", "user_id", "type", "date", "content"]


def results_to_dataframe(raw_results: list[dict]) -> pd.DataFrame:
    """Konversi list of dict ke DataFrame (dedup user_id+content, urutkan kolom)."""
    df = pd.DataFrame(raw_results)
    if not df.empty:
        if "user_id" in df.columns and "content" in df.columns:
            df = df.drop_duplicates(subset=["user_id", "content"])
            df = df.reset_index(drop=True)
        # Susun urutan kolom sesuai standar
        ordered_cols = [c for c in STANDARD_SCRAPER_COLUMNS if c in df.columns] + [
            c for c in df.columns if c not in STANDARD_SCRAPER_COLUMNS
        ]
        df = df[ordered_cols]
    return df


def save_dataframe(df: pd.DataFrame, path: str):
    """Simpan DataFrame ke CSV (UTF-8 BOM); direktori dibuat otomatis bila belum ada."""
    dirname = os.path.dirname(path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    if not df.empty:
        ordered_cols = [c for c in STANDARD_SCRAPER_COLUMNS if c in df.columns] + [
            c for c in df.columns if c not in STANDARD_SCRAPER_COLUMNS
        ]
        df = df[ordered_cols]
    df.to_csv(path, index=False, encoding="utf-8-sig")
    logger.info(f"Dataset tersimpan: {path} ({len(df)} baris)")


def append_checkpoint(results: list[dict], path: str):
    """Append baris baru ke CSV checkpoint (header ditulis bila file belum ada)."""
    if not results:
        return
    dirname = os.path.dirname(path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    df = pd.DataFrame(results)
    if not df.empty:
        ordered_cols = [c for c in STANDARD_SCRAPER_COLUMNS if c in df.columns] + [
            c for c in df.columns if c not in STANDARD_SCRAPER_COLUMNS
        ]
        df = df[ordered_cols]
    file_exists = os.path.exists(path)
    df.to_csv(path, mode="a", index=False, header=not file_exists, encoding="utf-8-sig")
    logger.info(f"Checkpoint: +{len(results)} baris ditambahkan ke '{path}'.")


def check_profile_exists(profile_dir: str) -> bool:
    """True bila direktori profil browser ada dan berisi data."""
    p = Path(profile_dir)
    if not p.exists() or not p.is_dir():
        return False
    try:
        return any(p.iterdir())
    except Exception:
        return False


# Filter Teks Bersama — dipakai oleh x_scraper & threads_scraper

def keyword_matches_text(text: str, keywords: list[str]) -> bool:
    """True bila teks mengandung salah satu keyword (case-insensitive, spasi diabaikan)."""
    # Teks kosong / kartu media dianggap valid karena berasal dari hasil search resmi platform
    if not text or not text.strip():
        return True

    text_lower    = text.lower()
    text_no_space = text_lower.replace(" ", "")
    for kw in keywords:
        clean          = kw.lstrip('#').lower()
        clean_no_space = clean.replace(" ", "")
        if clean in text_lower or (clean_no_space and clean_no_space in text_no_space):
            return True
        # Dukungan kecocokan kata individual untuk query majemuk
        words = [w for w in clean.split() if len(w) > 2]
        if words and any(w in text_lower for w in words):
            return True
    return False


def is_system_text(content: str, phrases: frozenset[str] | set[str]) -> bool:
    """True bila teks persis sama dengan salah satu frasa antarmuka sistem platform."""
    return content.strip().lower() in phrases
