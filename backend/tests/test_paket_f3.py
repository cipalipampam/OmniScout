
from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def modul(nama: str):
    return importlib.import_module(nama)


class KonsolidasiScraperTest(unittest.TestCase):
    """Duplikasi 100% identik harus berakhir di satu tempat (base_scraper)."""

    def test_keyword_matcher_dipakai_bersama(self):
        base = modul("src.scraping.base_scraper")
        x = modul("src.scraping.x_scraper")
        threads = modul("src.scraping.threads_scraper")

        self.assertTrue(
            hasattr(base, "keyword_matches_text"),
            "Implementasi bersama keyword_matches_text belum ada di base_scraper.",
        )
        self.assertIs(x.keyword_matches_text, base.keyword_matches_text)
        self.assertIs(threads.keyword_matches_text, base.keyword_matches_text)

    def test_perilaku_keyword_matcher_tidak_berubah(self):
        match = modul("src.scraping.base_scraper").keyword_matches_text

        # Teks kosong / media dianggap valid (berasal dari search resmi platform)
        self.assertTrue(match("", ["korupsi"]))
        self.assertTrue(match("   ", ["korupsi"]))
        # Case-insensitive, hashtag, dan query majemuk
        self.assertTrue(match("Korupsi lagi di negeri ini", ["korupsi"]))
        self.assertTrue(match("seru #Korupsi", ["#korupsi"]))
        self.assertTrue(match("tagar ruu polri ramai", ["RUU Polri"]))
        self.assertTrue(match("para pejabat korup", ["korupsi", "korup"]))
        # Tidak cocok
        self.assertFalse(match("cuaca hari ini cerah sekali", ["korupsi"]))

    def test_filter_teks_sistem_memakai_himpunan_frasa(self):
        sys_text = modul("src.scraping.base_scraper").is_system_text

        self.assertTrue(sys_text("  Log In ", {"log in"}))
        self.assertFalse(sys_text("log in dulu baru bisa komentar", {"log in"}))
        self.assertFalse(sys_text("kalimat biasa", {"log in"}))

    def test_setiap_scraper_tetap_punya_filter_satu_argumen(self):
        """Call site lama `is_system_text(content)` harus tetap bekerja."""
        for nama_modul in ("src.scraping.x_scraper", "src.scraping.threads_scraper"):
            m = modul(nama_modul)
            frasa = next(iter(m.SYSTEM_EXACT_PHRASES))
            self.assertTrue(m.is_system_text(frasa.upper()), f"{nama_modul} gagal mendeteksi frasa sistem.")
            self.assertFalse(m.is_system_text("teks pengguna biasa"), f"{nama_modul} salah anggap teks biasa.")

    def test_browser_factory_tunggal(self):
        base = modul("src.scraping.base_scraper")
        login_x = modul("src.auth.login_x")
        login_threads = modul("src.auth.login_threads")

        self.assertIs(login_x.create_browser, base.create_browser)
        self.assertIs(login_threads.create_browser, base.create_browser)


class KonsistensiKolomTeksTest(unittest.TestCase):
    def test_preprocessing_wajib_mempertahankan_teks_dan_merapikan_whitespace(self):
        import pandas as pd

        pipeline = modul("src.pipeline.end_to_end_pipeline").EndToEndPipeline()
        raw = pd.DataFrame({
            "platform": ["X", "X"],
            "user_id": ["u", "u"],
            "content": ["  HELLO!!!  ", "HELLO!!!"],
        })
        unchanged = pipeline.execute_preprocessing(raw)
        self.assertIn("content", unchanged.columns)
        self.assertNotIn("clean_text", unchanged.columns)
        self.assertEqual(1, len(unchanged))
        self.assertEqual("HELLO!!!", unchanged.loc[0, "content"])


class ConfigHeadlessTest(unittest.TestCase):
    def test_kunci_headless_mati_sudah_dihapus(self):
        from configs.config import SCRAPER_CONFIG

        self.assertNotIn(
            "headless",
            SCRAPER_CONFIG,
            "SCRAPER_CONFIG['headless'] tidak pernah dibaca siapa pun; headless dikendalikan per-request.",
        )

    def test_default_headless_scraper_eksplisit(self):
        x_cfg = modul("src.scraping.x_scraper").XScrapeConfig()
        t_cfg = modul("src.scraping.threads_scraper").ThreadsScrapeConfig()

        self.assertIs(True, x_cfg.headless)
        self.assertIs(True, t_cfg.headless)


if __name__ == "__main__":
    unittest.main(verbosity=2)
