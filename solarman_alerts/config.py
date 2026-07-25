from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
SECRETS_DIR = ROOT_DIR / ".secrets"
DATA_DIR = ROOT_DIR / "data"
STORAGE_STATE_PATH = SECRETS_DIR / "storage_state.json"
STATE_FILE_PATH = DATA_DIR / "state.json"
LOG_FILE_PATH = DATA_DIR / "solarman_alerts.log"

load_dotenv(ROOT_DIR / ".env")


def _env(name: str, default: str) -> str:
    # No GitHub Actions, uma env var referenciando uma variable/secret
    # inexistente ainda chega como string vazia (não None) — trata como
    # "não configurado" para não quebrar os defaults.
    value = os.getenv(name)
    return default if value is None or value == "" else value


def _bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Config:
    username: str
    password: str
    base_url: str
    station_ids: list[str]
    bootstrap_refresh_token: str

    start_threshold_w: float
    end_threshold_w: float
    end_confirmations: int
    end_not_before: str

    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_use_tls: bool
    email_from: str
    email_to: list[str] = field(default_factory=list)

    timezone: ZoneInfo = field(default_factory=lambda: ZoneInfo("UTC"))

    @property
    def has_email_configured(self) -> bool:
        return bool(self.smtp_host and self.email_from and self.email_to)

    @property
    def has_credentials(self) -> bool:
        return bool(self.username and self.password)


def load_config() -> Config:
    tz_name = _env("LOCAL_TIMEZONE", "UTC")
    return Config(
        username=_env("SOLARMAN_USERNAME", ""),
        password=_env("SOLARMAN_PASSWORD", ""),
        base_url=_env("SOLARMAN_BASE_URL", "https://home.solarmanpv.com").rstrip("/"),
        station_ids=_list(os.getenv("SOLARMAN_STATION_IDS")),
        bootstrap_refresh_token=_env("SOLARMAN_REFRESH_TOKEN", ""),
        start_threshold_w=float(_env("PRODUCTION_START_THRESHOLD_W", "20")),
        end_threshold_w=float(_env("PRODUCTION_END_THRESHOLD_W", "5")),
        end_confirmations=int(_env("PRODUCTION_END_CONFIRMATIONS", "3")),
        end_not_before=_env("PRODUCTION_END_NOT_BEFORE", "10:00"),
        smtp_host=_env("SMTP_HOST", ""),
        smtp_port=int(_env("SMTP_PORT", "587")),
        smtp_username=_env("SMTP_USERNAME", ""),
        smtp_password=_env("SMTP_PASSWORD", ""),
        smtp_use_tls=_bool(os.getenv("SMTP_USE_TLS"), True),
        email_from=_env("ALERT_EMAIL_FROM", ""),
        email_to=_list(os.getenv("ALERT_EMAIL_TO")),
        timezone=ZoneInfo(tz_name),
    )
