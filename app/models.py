from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Participant(BaseModel):
    name: str
    email: str | None = None


class ReadAIWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    participants: list[Any] = Field(default_factory=list)
    transcript: Any = None
    summary: Any = None
    action_items: list[Any] = Field(default_factory=list)
    chapter_summaries: list[Any] = Field(default_factory=list)
    meeting_id: str | None = None
    meeting_title: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None


class ParsedMeeting(BaseModel):
    participants: list[Participant]
    transcript: str
    source_summary: str | None = None
    meeting_date: date
    raw_payload: dict[str, Any]


class LLMSummary(BaseModel):
    summary: str
    observations: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    mood: str | None = None
    topics: list[str] = Field(default_factory=list)


class NotionPageResult(BaseModel):
    page_id: str
    url: str | None = None


class WebhookResult(BaseModel):
    status: Literal["ok", "skipped"] = "ok"
    report_name: str | None = None
    notion_page_id: str | None = None
    notion_url: str | None = None
    meeting_date: date | None = None
    skip_reason: str | None = None
