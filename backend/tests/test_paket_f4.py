
from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

README = BACKEND_DIR / "README.md"

# Endpoint yang TIDAK ADA di kode dan tidak boleh muncul lagi di dokumentasi.
ENDPOINT_HANTU = (
    "/api/v1/preprocess/clean",
    "/api/v1/preprocess/single",
    "/api/v1/preprocess/batch",
    "/api/v1/scrape/run",
    "/api/v1/scrape/status/{job_id}",
    "/api/v1/scrape/x",
    "/api/v1/scrape/threads",
    "/api/v1/classify/info",
    "/api/v1/classify/batch",
    "/api/v1/auth/sessions",
    "/api/v1/auth/login-browser",
)

# `/api/v1/pipeline/exports` (daftar berkas) sudah dihapus, tetapi string-nya adalah
# awalan dari `/api/v1/pipeline/exports/{filename}` yang MASIH ada — jadi diperiksa
# sebagai token berbacktick, bukan substring bebas.
ENDPOINT_HANTU_TOKEN = ("/api/v1/pipeline/exports",)


def fake_is_session_valid(platform: str) -> dict:
    """Hanya sesi Threads yang valid (untuk menguji kedua platform)."""
    return {"is_valid": platform == "threads", "message": "sesi palsu untuk uji"}


class KebijakanSesiTunggalTest(unittest.TestCase):
    def setUp(self):
        self.pipeline_mod = importlib.import_module("src.pipeline.end_to_end_pipeline")

        self._patch = patch.object(self.pipeline_mod, "is_session_valid", fake_is_session_valid)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_fungsi_bersama_tersedia(self):
        self.assertTrue(
            hasattr(self.pipeline_mod, "validate_platform_sessions"),
            "Kebijakan validasi sesi belum dipindah ke satu fungsi bersama.",
        )

    def test_hasil_validasi_sesuai_kebijakan(self):
        validasi = self.pipeline_mod.validate_platform_sessions

        self.assertEqual((True, []), validasi("threads"))
        self.assertEqual((True, []), validasi("THREADS "))  # normalisasi platform

        valid, errors = validasi("x")
        self.assertFalse(valid)
        self.assertEqual(1, len(errors))
        self.assertIn("login-trigger/x", errors[0])

        valid_both, errors_both = validasi("both")
        self.assertFalse(valid_both)
        self.assertEqual(1, len(errors_both), f"Hanya X yang invalid, error: {errors_both}")

    def test_validate_sessions_tidak_menyertakan_status_terpakai(self):
        tahap = self.pipeline_mod.EndToEndPipeline()

        hasil = tahap.validate_sessions("both")

        self.assertEqual({"valid", "errors"}, set(hasil), f"Key tak terpakai muncul lagi: {set(hasil)}")
        self.assertFalse(hasil["valid"])
        self.assertEqual(1, len(hasil["errors"]))
        self.assertIn("login-trigger", hasil["errors"][0])

    def test_tidak_ada_scan_status_tambahan(self):
        sumber = (BACKEND_DIR / "src" / "pipeline" / "end_to_end_pipeline.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "get_all_sessions_status",
            sumber,
            "validate_sessions() memanggil get_all_sessions_status() (scan filesystem tambahan yang tidak dipakai).",
        )


class DokumentasiEndpointTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.readme_backend = (BACKEND_DIR / "README.md").read_text(encoding="utf-8")
        root_readme = BACKEND_DIR.parent / "README.md"
        cls.readme_root = root_readme.read_text(encoding="utf-8") if root_readme.exists() else ""
        cls.nyata = set(importlib.import_module("main_api").app.openapi().get("paths", {}))

    def test_semua_endpoint_nyata_terdokumentasi(self):
        hilang = sorted(p for p in self.nyata if p not in self.readme_backend)
        self.assertEqual([], hilang, f"Endpoint ini tidak tercantum di README backend: {hilang}")

    def test_tidak_ada_endpoint_hantu_di_kedua_readme(self):
        readme = (("backend/README.md", self.readme_backend), ("README.md (root)", self.readme_root))
        for label, teks in readme:
            hantu = [p for p in ENDPOINT_HANTU if p in teks]
            self.assertEqual([], hantu, f"{label} masih mencantumkan endpoint yang tidak ada: {hantu}")

            token = [p for p in ENDPOINT_HANTU_TOKEN if f"`{p}`" in teks]
            self.assertEqual([], token, f"{label} masih mencantumkan endpoint daftar ekspor yang sudah dihapus: {token}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
