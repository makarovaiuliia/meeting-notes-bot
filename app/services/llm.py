from __future__ import annotations

import json

import httpx

from app.config import Settings
from app.models import LLMSummary


SYSTEM_PROMPT = (
    "Ты анализируешь транскрипты 1:1 встреч менеджера с репортом. "
    "Верни строго JSON с полями summary, observations, decisions, mood, topics. "
    "summary должен быть кратким саммари на русском языке. "
    "observations и decisions должны быть массивами строк. "
    "mood должен быть одним словом, без запятых и без пояснений. "
    "topics должен быть массивом очень коротких тем, каждая тема 1-2 слова максимум."
)



class LLMService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def summarize_meeting(self, transcript: str, source_summary: str | None) -> LLMSummary:
        payload = {
            "model": self._settings.llm_model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": self._build_user_prompt(transcript, source_summary),
                },
            ],
        }

        headers = {
            "Authorization": f"Bearer {self._settings.llm_api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self._settings.llm_base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()

        content = _clean_json_text(_extract_message_content(response.json()))
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError("LLM response is not valid JSON") from exc
        return LLMSummary.model_validate(parsed)

    def _build_user_prompt(self, transcript: str, source_summary: str | None) -> str:
        prompt = (
            "Это транскрипт 1:1 встречи. Сделай краткое саммари на русском языке: "
            "основные наблюдения, ключевые решения, настроение встречи и темы. "
            "Верни JSON с полями: summary, observations[], decisions[], mood, topics[].\n"
            "Требования: mood — одно слово, без запятых. "
            "Каждый элемент topics — очень короткий, 1-2 слова максимум, без запятых.\n\n"
        )
        if source_summary:
            prompt += f"Саммари от Read AI:\n{source_summary}\n\n"
        prompt += f"Транскрипт встречи:\n{transcript}"
        return prompt


def _extract_message_content(response_payload: dict) -> str:
    choices = response_payload.get("choices")
    if not choices:
        raise ValueError("LLM response does not contain choices")

    message = choices[0].get("message") or {}
    content = message.get("content")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
        if text_parts:
            return "\n".join(text_parts)

    raise ValueError("LLM response message.content is empty or unsupported")

def _clean_json_text(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped
