from __future__ import annotations

import logging
from typing import Any

import structlog
from fastapi import FastAPI, Header, HTTPException, Request, status

from app.config import get_settings
from app.models import WebhookResult
from app.services.llm import LLMService
from app.services.notion import NotionService
from app.services.readai import (
    get_human_participants,
    is_one_on_one_meeting,
    load_json_body,
    parse_payload,
    resolve_report_participant,
    verify_signature,
)


def configure_logging() -> None:
    logging.basicConfig(
        format="%(message)s",
        level=logging.INFO,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


configure_logging()
logger = structlog.get_logger(__name__)
app = FastAPI(title="Meeting Notes Bot")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook/readai", response_model=WebhookResult)
async def readai_webhook(
    request: Request,
    x_read_signature: str | None = Header(default=None, alias="X-Read-Signature"),
) -> WebhookResult:
    settings = get_settings()
    body = await request.body()

    if not verify_signature(settings.readai_webhook_secret, body, x_read_signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Read AI signature",
        )

    payload = load_json_body(body)
    return await _process_payload(payload, source="readai")


@app.post("/webhook/test", response_model=WebhookResult)
async def test_webhook(payload: dict[str, Any]) -> WebhookResult:
    return await _process_payload(payload, source="test")


async def _process_payload(payload: dict[str, Any], source: str) -> WebhookResult:
    settings = get_settings()

    try:
        meeting = parse_payload(payload)
        human_participants = get_human_participants(meeting.participants)
        if not is_one_on_one_meeting(meeting.participants):
            logger.info(
                "webhook_skipped_non_one_on_one",
                source=source,
                meeting_date=meeting.meeting_date.isoformat(),
                participant_count=len(human_participants),
                participants=[participant.name for participant in human_participants],
            )
            return WebhookResult(
                status="skipped",
                meeting_date=meeting.meeting_date,
                skip_reason="Meeting is not a 1:1",
            )

        report_name, report_page_id = resolve_report_participant(human_participants, settings)
    except ValueError as exc:
        logger.warning("payload_validation_failed", source=source, error=str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    logger.info(
        "webhook_received",
        source=source,
        report_name=report_name,
        meeting_date=meeting.meeting_date.isoformat(),
        participant_count=len(human_participants),
    )

    llm_service = LLMService(settings)
    notion_service = NotionService(settings)

    try:
        llm_summary = await llm_service.summarize_meeting(
            transcript=meeting.transcript,
            source_summary=meeting.source_summary,
        )
    except Exception as exc:
        logger.exception("llm_processing_failed", source=source, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to summarize meeting with LLM",
        ) from exc

    try:
        notion_page = await notion_service.create_one_on_one_page(
            report_name=report_name,
            report_page_id=report_page_id,
            meeting_date=meeting.meeting_date,
            llm_summary=llm_summary,
        )
    except Exception as exc:
        logger.exception("notion_create_failed", source=source, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to create Notion page",
        ) from exc

    logger.info(
        "webhook_processed",
        source=source,
        report_name=report_name,
        notion_page_id=notion_page.page_id,
    )

    return WebhookResult(
        report_name=report_name,
        notion_page_id=notion_page.page_id,
        notion_url=notion_page.url,
        meeting_date=meeting.meeting_date,
    )
