from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.schemas.scrape_schema import ScrapeRunRequest
from app.services.job_service import JobManager
from app.services.pipeline_service import PipelineService, pipeline_service
import app.services.pipeline_service  # noqa: F401

pipeline_service_module = sys.modules["app.services.pipeline_service"]


class JobManagerEvictionTest(unittest.TestCase):
    def test_active_jobs_are_not_evicted(self):
        manager = JobManager(max_jobs=2)
        manager.create_job("active", "scrape", {})
        manager.update_job("active", status="running")
        manager.create_job("queued", "scrape", {})
        manager.create_job("new", "scrape", {})
        self.assertIsNotNone(manager.get_job("active"))
        self.assertIsNotNone(manager.get_job("new"))

    def test_finished_jobs_are_evicted_first(self):
        manager = JobManager(max_jobs=2)
        manager.create_job("finished", "scrape", {})
        manager.update_job("finished", status="success")
        manager.create_job("active", "scrape", {})
        manager.update_job("active", status="running")
        manager.create_job("new", "scrape", {})
        self.assertIsNone(manager.get_job("finished"))
        self.assertIsNotNone(manager.get_job("active"))


class ScrapeSchemaTest(unittest.TestCase):
    def test_keyword_or_direct_url_is_required(self):
        with self.assertRaises(ValueError):
            ScrapeRunRequest(keywords=[], direct_urls=[])

    def test_direct_url_is_supported_without_keyword(self):
        request = ScrapeRunRequest(
            keywords=[],
            direct_urls=[" https://x.com/example/status/1 "],
        )
        self.assertEqual(["https://x.com/example/status/1"], request.direct_urls)


class SafeExportPathTest(unittest.TestCase):
    def test_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            export_dir = Path(directory)
            (export_dir / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
            with patch.object(pipeline_service_module, "EXPORTS_DIR", export_dir):
                self.assertIsNotNone(PipelineService.get_safe_export_path("data.csv"))
                self.assertIsNone(PipelineService.get_safe_export_path("../secret.csv"))


class ScrapeStatisticsTest(unittest.IsolatedAsyncioTestCase):
    async def test_scrape_job_statistics(self):
        class FakePipeline:
            async def run(self, **kwargs):
                return {
                    "status": "success",
                    "total_data": 2,
                    "statistics": {
                        "total_data": 2,
                        "unique_users": 2,
                        "unique_sources": 2,
                        "platform_breakdown": {
                            "X": {"total": 2, "unique_users": 2, "original_posts": 1, "comments": 1}
                        },
                        "type_breakdown": {"Original Post": 1, "Comment": 1},
                    },
                    "exported_file": None,
                }

        with patch.object(pipeline_service_module, "EndToEndPipeline", FakePipeline):
            request = ScrapeRunRequest(keywords=["uji"], platform="x")
            job = await pipeline_service.create_and_start_pipeline_job(request)
            status = None
            for _ in range(100):
                status = pipeline_service.get_job_status(job.job_id)
                if status.status in ("success", "error"):
                    break
                await asyncio.sleep(0.01)

        self.assertEqual("success", status.status)
        self.assertEqual(2, status.statistics.total_data)
        self.assertEqual(2, status.statistics.platform_breakdown["X"].unique_users)


if __name__ == "__main__":
    unittest.main(verbosity=2)
