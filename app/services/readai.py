from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import date, datetime, timezone
from typing import Any

from pydantic import TypeAdapter

from app.config import Settings, normalize_name
from app.models import ParsedMeeting, Participant, ReadAIWebhookPayload


DATETIME_ADAPTER = TypeAdapter(datetime)
DATE_ADAPTER = TypeAdapter(date)
SYSTEM_PARTICIPANT_MARKERS = (
    "read ai",
    "readai",
    "notetaker",
    "note taker",
)


def verify_signature(secret: str, body: bytes, provided_signature: str | None) -> bool:
    if not provided_signature:
        return False

    provided_signature = provided_signature.strip()
    if provided_signature.startswith("sha256="):
        provided_signature = provided_signature.split("=", maxsplit=1)[1]

    try:
        signing_key = base64.b64decode(secret)
    except Exception:
        signing_key = secret.encode("utf-8")

    digest = hmac.new(signing_key, body, hashlib.sha256).digest()
    expected_hex = digest.hex()
    expected_base64 = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected_hex, provided_signature) or hmac.compare_digest(
        expected_base64,
        provided_signature,
    )


def parse_payload(raw_payload: dict[str, Any]) -> ParsedMeeting:
    payload = ReadAIWebhookPayload.model_validate(raw_payload)
    participants = _extract_participants(payload, raw_payload)
    transcript = _extract_text_field(raw_payload, ["transcript", "transcript_text", "full_transcript"])
    summary = _extract_text_field(raw_payload, ["summary", "meeting_summary"])
    meeting_date = _extract_meeting_date(payload, raw_payload)

    if not participants:
        raise ValueError("Could not extract participants from Read AI payload")
    if not transcript:
        raise ValueError("Could not extract transcript from Read AI payload")

    return ParsedMeeting(
        participants=participants,
        transcript=transcript,
        source_summary=summary or None,
        meeting_date=meeting_date,
        raw_payload=raw_payload,
    )


def resolve_report_participant(
    participants: list[Participant],
    settings: Settings,
) -> tuple[str, str]:
    for participant in participants:
        page_id = settings.normalized_team_mapping.get(normalize_name(participant.name))
        if page_id:
            return participant.name, page_id

    participant_names = ", ".join(participant.name for participant in participants)
    raise ValueError(
        "Could not match any participant to TEAM_MAPPING. "
        f"Participants: {participant_names}"
    )


def get_human_participants(participants: list[Participant]) -> list[Participant]:
    human_participants: list[Participant] = []
    seen_names: set[str] = set()

    for participant in participants:
        normalized_name = normalize_name(participant.name)
        if not normalized_name or _is_system_participant(normalized_name):
            continue
        if normalized_name in seen_names:
            continue
        seen_names.add(normalized_name)
        human_participants.append(participant)

    return human_participants


def is_one_on_one_meeting(participants: list[Participant]) -> bool:
    return len(get_human_participants(participants)) == 2


def _extract_participants(
    payload: ReadAIWebhookPayload,
    raw_payload: dict[str, Any],
) -> list[Participant]:
    source = payload.participants or raw_payload.get("attendees") or raw_payload.get("speakers") or []
    participants: list[Participant] = []

    for item in source:
        participant = _coerce_participant(item)
        if participant:
            participants.append(participant)

    return participants


def _coerce_participant(value: Any) -> Participant | None:
    if isinstance(value, str):
        name = value.strip()
        return Participant(name=name) if name else None

    if isinstance(value, dict):
        candidate_names = [
            value.get("name"),
            value.get("display_name"),
            value.get("full_name"),
            value.get("participant_name"),
        ]
        for candidate in candidate_names:
            if isinstance(candidate, str) and candidate.strip():
                return Participant(name=candidate.strip(), email=_extract_email(value))

    return None


def _is_system_participant(normalized_name: str) -> bool:
    return any(marker in normalized_name for marker in SYSTEM_PARTICIPANT_MARKERS)


def _extract_email(value: dict[str, Any]) -> str | None:
    for key in ("email", "mail"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _extract_text_field(raw_payload: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        if key in raw_payload:
            text = _flatten_text(raw_payload[key])
            if text:
                return text
    return ""


def _flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [_flatten_text(item) for item in value]
        return "\n".join(part for part in parts if part).strip()
    if isinstance(value, dict):
        for key in ("text", "content", "summary", "transcript"):
            candidate = value.get(key)
            text = _flatten_text(candidate)
            if text:
                return text

        if "segments" in value:
            return _flatten_text(value["segments"])
        if "items" in value:
            return _flatten_text(value["items"])

        text_parts: list[str] = []
        for candidate in value.values():
            text = _flatten_text(candidate)
            if text:
                text_parts.append(text)
        return "\n".join(text_parts).strip()

    return ""


def _extract_meeting_date(
    payload: ReadAIWebhookPayload,
    raw_payload: dict[str, Any],
) -> date:
    candidates = [
        payload.start_time,
        payload.end_time,
        raw_payload.get("start_time"),
        raw_payload.get("started_at"),
        raw_payload.get("scheduled_at"),
        raw_payload.get("date"),
        raw_payload.get("created_at"),
        raw_payload.get("ended_at"),
    ]

    for candidate in candidates:
        parsed = _parse_datetime_or_date(candidate)
        if parsed:
            return parsed.date()

    return datetime.now(timezone.utc).date()


def _parse_datetime_or_date(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        normalized = stripped.replace("Z", "+00:00")
        try:
            return DATETIME_ADAPTER.validate_python(normalized)
        except Exception:
            try:
                parsed_date = DATE_ADAPTER.validate_python(normalized)
                return datetime.combine(parsed_date, datetime.min.time())
            except Exception:
                return None
    return None


def load_json_body(body: bytes) -> dict[str, Any]:
    try:
        parsed = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Webhook body is not valid JSON") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Webhook body must be a JSON object")

    return parsed
