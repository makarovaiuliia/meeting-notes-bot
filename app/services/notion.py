from __future__ import annotations

from datetime import date

from notion_client import AsyncClient

from app.config import Settings
from app.models import LLMSummary, NotionPageResult


MAX_RICH_TEXT_CHARS = 1800


class NotionService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncClient(auth=settings.notion_token)

    async def create_one_on_one_page(
        self,
        report_name: str,
        report_page_id: str,
        meeting_date: date,
        llm_summary: LLMSummary,
    ) -> NotionPageResult:
        properties = {
            "Title": {
                "title": [
                    {
                        "text": {
                            "content": f"1:1 with {report_name}",
                        }
                    }
                ]
            },
            "Date": {"date": {"start": meeting_date.isoformat()}},
            "Report": {"relation": [{"id": report_page_id}]},
            "Mood": {"select": {"name": _short_mood(llm_summary.mood)}} if llm_summary.mood else {"select": None},
            "Topics": {
                "multi_select": [
                    {"name": _short_topic(item)}
                    for item in llm_summary.topics
                    if item.strip()
                ]
            },
        }

        response = await self._client.pages.create(
            parent={"database_id": self._settings.notion_11_database_id},
            icon={"type": "emoji", "emoji": "👤"},
            properties=properties,
            children=_build_children(llm_summary),
        )

        return NotionPageResult(
            page_id=response["id"],
            url=response.get("url"),
        )


def _build_children(llm_summary: LLMSummary) -> list[dict]:
    children: list[dict] = []
    children.extend(_heading("Summary"))
    children.extend(_paragraphs(llm_summary.summary))

    if llm_summary.observations:
        children.extend(_heading("Observations"))
        children.extend(_bullets(llm_summary.observations))

    if llm_summary.decisions:
        children.extend(_heading("Decisions"))
        children.extend(_bullets(llm_summary.decisions))

    return children


def _heading(text: str) -> list[dict]:
    return [
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": text},
                    }
                ]
            },
        }
    ]


def _paragraphs(text: str) -> list[dict]:
    return [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": chunk},
                    }
                ]
            },
        }
        for chunk in _chunk_text(text)
        if chunk
    ]


def _bullets(items: list[str]) -> list[dict]:
    blocks: list[dict] = []
    for item in items:
        for chunk in _chunk_text(item):
            if not chunk:
                continue
            blocks.append(
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": chunk},
                            }
                        ]
                    },
                }
            )
    return blocks


def _chunk_text(text: str) -> list[str]:
    normalized = " ".join(text.split())
    if not normalized:
        return []

    chunks: list[str] = []
    remaining = normalized
    while remaining:
        if len(remaining) <= MAX_RICH_TEXT_CHARS:
            chunks.append(remaining)
            break

        split_at = remaining.rfind(" ", 0, MAX_RICH_TEXT_CHARS)
        if split_at <= 0:
            split_at = MAX_RICH_TEXT_CHARS
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()

    return chunks

def _short_mood(value: str) -> str:
    words = value.replace(",", " ").split()
    if not words:
        return "Neutral"
    return words[0][:30]


def _short_topic(value: str) -> str:
    words = value.replace(",", " ").split()
    if not words:
        return ""
    return " ".join(words[:2])[:40]
