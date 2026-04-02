import json
import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


load_dotenv()


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"Environment variable {name} is required")
    return value.strip()


def _get_env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()


def _parse_bool_env(name: str, default: bool = False) -> bool:
    value = _get_env(name)
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _parse_team_mapping(raw_value: str) -> dict[str, str]:
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise RuntimeError("TEAM_MAPPING must be valid JSON") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError("TEAM_MAPPING must be a JSON object")

    mapping: dict[str, str] = {}
    for name, page_id in parsed.items():
        if not isinstance(name, str) or not isinstance(page_id, str):
            raise RuntimeError("TEAM_MAPPING keys and values must be strings")
        mapping[name.strip()] = page_id.strip()
    return mapping


def normalize_name(value: str) -> str:
    return " ".join(value.split()).casefold()


@dataclass(frozen=True)
class Settings:
    notion_token: str
    notion_11_database_id: str
    notion_reports_database_id: str
    notion_tasks_database_id: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    readai_webhook_secret: str
    readai_skip_signature_verification: bool
    team_mapping: dict[str, str]

    @property
    def normalized_team_mapping(self) -> dict[str, str]:
        return {
            normalize_name(name): page_id
            for name, page_id in self.team_mapping.items()
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        notion_token=_require_env("NOTION_TOKEN"),
        notion_11_database_id=_require_env("NOTION_11_DATABASE_ID"),
        notion_reports_database_id=_require_env("NOTION_REPORTS_DATABASE_ID"),
        notion_tasks_database_id=_require_env("NOTION_TASKS_DATABASE_ID"),
        llm_base_url=_require_env("LLM_BASE_URL").rstrip("/"),
        llm_api_key=_require_env("LLM_API_KEY"),
        llm_model=_require_env("LLM_MODEL"),
        readai_webhook_secret=_get_env("READAI_WEBHOOK_SECRET"),
        readai_skip_signature_verification=_parse_bool_env("READAI_SKIP_SIGNATURE_VERIFICATION"),
        team_mapping=_parse_team_mapping(_require_env("TEAM_MAPPING")),
    )
