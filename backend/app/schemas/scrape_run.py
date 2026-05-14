from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ScrapeRunSummary(BaseModel):
    run_id: UUID = Field(alias="runId")
    status: str
    mode: str = "incremental"
    row_count: int = Field(alias="rowCount")
    total_count: int = Field(default=0, alias="totalCount")
    processed_count: int = Field(default=0, alias="processedCount")
    inserted_count: int = Field(default=0, alias="insertedCount")
    updated_count: int = Field(default=0, alias="updatedCount")
    skipped_count: int = Field(default=0, alias="skippedCount")
    detail_failed_count: int = Field(default=0, alias="detailFailedCount")
    started_at: datetime | None = Field(default=None, alias="startedAt")
    finished_at: datetime | None = Field(default=None, alias="finishedAt")
    error_message: str | None = Field(default=None, alias="errorMessage")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ScrapeStatusResponse(BaseModel):
    latest_run: ScrapeRunSummary | None = Field(default=None, alias="latestRun")

    model_config = ConfigDict(populate_by_name=True)
