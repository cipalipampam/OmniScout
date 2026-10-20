
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Kontrak API yang dipakai frontend Laravel (FastAPIClientService) + endpoint yang masih punya konsumen.
# Catatan (2026-09-25): `/classify/info`, `/classify/batch`, `/preprocess/*`, `/scrape/*`,
# dan `/pipeline/exports` (daftar berkas) DIHAPUS karena tidak ada konsumennya.
ENDPOINT_DIHARAPKAN = {
    # Auth
    "/api/v1/auth/status",
    "/api/v1/auth/login-trigger/{platform}",
    # Pipeline
    "/api/v1/pipeline/run",
    "/api/v1/pipeline/status/{job_id}",
    "/api/v1/pipeline/exports/{filename}",
    # Health & root (root dipakai healthcheck docker-compose.yml)
    "/api/v1/health",
    "/",
}
# CATATAN: /openapi.json, /docs, /docs/oauth2-redirect, /redoc TIDAK muncul di
# `app.openapi()["paths"]` karena bukan operasi API (hanya UI dokumentasi), sehingga
# keberadaannya diverifikasi terpisah lewat `app.routes`.


class EndpointInventoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import main_api

        cls.app = main_api.app

    def test_inventaris_endpoint_tidak_berubah(self):
        # Sumber kebenaran = OpenAPI. `app.routes` tidak bisa dipakai karena FastAPI 0.141
        # membungkus hasil include_router sebagai `_IncludedRouter` tanpa atribut `path`.
        terdaftar = set(self.app.openapi().get("paths", {}))

        hilang = sorted(ENDPOINT_DIHARAPKAN - terdaftar)
        tambahan = sorted(terdaftar - ENDPOINT_DIHARAPKAN)

        self.assertEqual([], hilang, f"Endpoint hilang (breaking change untuk frontend): {hilang}")
        self.assertEqual([], tambahan, f"Endpoint baru tak terduga: {tambahan}; perbarui daftar kontrak bila disengaja.")

    def test_router_masih_terdaftar_lengkap(self):
        from app import routers

        for nama in ("auth_router", "pipeline_router"):
            obj = getattr(routers, nama, None)
            self.assertIsNotNone(obj, f"Barrel app.routers tidak lagi mengekspor {nama}.")
            self.assertTrue(getattr(obj, "routes", []), f"Router {nama} tidak punya route.")

    def test_ui_dokumentasi_masih_aktif(self):
        path_routes = {getattr(r, "path", None) for r in self.app.routes}
        for wajib in ("/openapi.json", "/docs", "/redoc"):
            self.assertIn(wajib, path_routes, f"UI dokumentasi {wajib} hilang dari app.routes.")


class CliEntrypointTest(unittest.TestCase):
    def test_main_cli_dapat_diimpor(self):
        """Pembersihan import mati tidak boleh memutus entrypoint CLI."""
        import importlib

        modul = importlib.import_module("main_cli")
        self.assertTrue(callable(getattr(modul, "main", None)), "main_cli.main tidak lagi callable.")

    def test_symbol_dead_tidak_kembali(self):
        """Penjaga agar dead code yang sudah dihapus tidak dihidupkan lagi tanpa alasan."""
        from app.services.auth_service import AuthService

        self.assertFalse(
            hasattr(AuthService, "check_display_available"),
            "check_display_available() adalah dead code — sumber kebenaran mode GUI adalah "
            "AuthService.get_login_environment().",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
