from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ScrapeRunRequest(BaseModel):
    """Parameter untuk menjalankan pengumpulan data X dan Threads."""

    keywords: List[str] = Field(default_factory=list, description="Keyword pencarian.")
    direct_urls: List[str] = Field(default_factory=list, description="URL posting/thread yang diproses langsung.")
    platform: Literal["x", "threads", "both"] = "both"
    search_mode: Literal["latest", "top"] = "latest"
    max_links: int = Field(default=50, ge=1, le=500)
    max_scroll_steps: int = Field(default=300, ge=50, le=5000)
    headless: bool = False
    export_csv: bool = True

    @field_validator("keywords", "direct_urls")
    @classmethod
    def strip_items(cls, value: List[str]) -> List[str]:
        return [item.strip() for item in value if item.strip()]

    @field_validator("direct_urls")
    @classmethod
    def validate_input(cls, value: List[str], info):
        keywords = info.data.get("keywords", [])
        if not keywords and not value:
            raise ValueError("Masukkan minimal satu keyword atau direct URL.")
        return value

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "keywords": ["RUU Polri"],
            "direct_urls": [],
            "platform": "both",
            "search_mode": "latest",
            "max_links": 50,
            "max_scroll_steps": 300,
            "headless": False,
            "export_csv": True,
        }
    })


class ScrapeJobResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running"] = "queued"
    message: str
    platform: str
    keywords: List[str]


class PlatformScrapeBreakdown(BaseModel):
    total: int = 0
    unique_users: int = 0
    original_posts: int = 0
    comments: int = 0


class ScrapeStatistics(BaseModel):
    total_data: int = 0
    unique_users: int = 0
    unique_sources: int = 0
    platform_breakdown: Dict[str, PlatformScrapeBreakdown] = Field(default_factory=dict)
    type_breakdown: Dict[str, int] = Field(default_factory=dict)


class ScrapeJobStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "success", "error"]
    message: str
    platform: Optional[str] = None
    keywords: Optional[List[str]] = None
    search_mode: Optional[str] = None
    total_data: int = 0
    elapsed_seconds: Optional[float] = None
    statistics: Optional[ScrapeStatistics] = None
    exported_file: Optional[str] = None
    error_detail: Optional[str] = None
