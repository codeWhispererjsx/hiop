from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ReportCard(BaseModel):
    key: str
    title: str
    total_records: int
    last_generated: datetime
    export_formats: list[str] = Field(default_factory=lambda: ["csv"])


class ReportsSummary(BaseModel):
    generated_at: datetime
    cards: list[ReportCard]


class ReportPage(BaseModel):
    report: str
    generated_at: datetime
    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int
    pages: int
    metrics: dict[str, Any]
    charts: dict[str, list[dict[str, Any]]]
