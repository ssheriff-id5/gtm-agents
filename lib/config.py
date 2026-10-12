"""Config loading and run-mode selection.

Run mode is **dry-run unless explicitly set live** (REVOPS_MODE=live). A missing
token in live mode is a hard error, never a silent fallback to dry-run: a run that
quietly does nothing is exactly the silent failure the job contract forbids.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"


class ConfigError(RuntimeError):
    pass


def is_dry_run() -> bool:
    return os.environ.get("REVOPS_MODE", "dry-run").strip().lower() != "live"


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is not set (required when REVOPS_MODE=live)")
    return value


@lru_cache(maxsize=None)
def _load(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def notion_config() -> dict:
    return _load("notion.yaml")


def team_config() -> dict:
    return _load("employees.yaml")["team"]


def humans() -> dict:
    return _load("humans.yaml").get("humans") or {}


@dataclass(frozen=True)
class Employee:
    key: str
    display_name: str
    title: str
    level: str
    reports_to: str
    notion_page_id: str
    slack_username: str
    icon_emoji: str | None
    icon_url: str | None
    schedule_description: str
    schedule_cron: str | None
    tasks: tuple[str, ...]


def get_employee(key: str) -> Employee:
    employees = _load("employees.yaml")["employees"]
    raw = employees.get(key.lower())
    if raw is None:
        raise ConfigError(f"Unknown employee '{key}'. Known: {', '.join(sorted(employees))}")
    slack = raw.get("slack") or {}
    schedule = raw.get("schedule") or {}
    return Employee(
        key=key.lower(),
        display_name=raw["display_name"],
        title=raw["title"],
        level=raw["level"],
        reports_to=raw["reports_to"],
        notion_page_id=raw["notion_page_id"],
        slack_username=slack.get("username") or raw["display_name"],
        icon_emoji=slack.get("icon_emoji"),
        icon_url=slack.get("icon_url"),
        schedule_description=schedule.get("description", ""),
        schedule_cron=schedule.get("cron"),
        tasks=tuple(raw.get("tasks") or ()),
    )


def all_employees() -> list[Employee]:
    return [get_employee(k) for k in _load("employees.yaml")["employees"]]


def team_tz() -> ZoneInfo:
    return ZoneInfo(team_config().get("timezone") or "UTC")


def today() -> date:
    return datetime.now(team_tz()).date()


def slack_channel() -> str:
    return os.environ.get("SLACK_CHANNEL_ID") or team_config()["slack_channel"]
