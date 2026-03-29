from __future__ import annotations

import os


def _get_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _parse_faults() -> set[str]:
    raw = os.getenv("AGENT_DEMO_FAULTS", "").strip()
    faults = {
        item.strip()
        for item in raw.split(",")
        if item.strip() and item.strip().lower() not in {"off", "false", "none"}
    }
    # backward compatibility for the previous single-bug toggle
    if _get_bool("AGENT_DEMO_SUBSCRIPTION_CACHE_BUG", "false"):
        faults.add("subscription_cache_bug")
    return faults


def demo_fault_enabled(name: str) -> bool:
    return name in AGENT_DEMO_FAULTS


GRAFANA_BASE_URL = os.getenv("GRAFANA_BASE_URL", "http://grafana:3000")
GRAFANA_ADMIN_USER = os.getenv("GRAFANA_ADMIN_USER", "admin")
GRAFANA_ADMIN_PASSWORD = os.getenv("GRAFANA_ADMIN_PASSWORD", "admin")

MYSQL_HOST = os.getenv("MYSQL_HOST", "mysql")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
MYSQL_USER = os.getenv("MYSQL_USER", "app")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "app")
MYSQL_DB = os.getenv("MYSQL_DB", "dashboard_hub")

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "120"))

AI_ENABLED = _get_bool("AI_ENABLED", "false")
AI_PROVIDER = os.getenv("AI_PROVIDER", "deepseek")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.deepseek.com/v1")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "deepseek-chat")
AI_TIMEOUT_SECONDS = int(os.getenv("AI_TIMEOUT_SECONDS", "20"))
AI_PROMPT_VERSION = os.getenv("AI_PROMPT_VERSION", "v1")
AI_MAX_SUMMARY_CHARS = int(os.getenv("AI_MAX_SUMMARY_CHARS", "120"))

AI_MAX_PANELS_TO_SUMMARIZE = int(os.getenv("AI_MAX_PANELS_TO_SUMMARIZE", "3"))
AI_MAX_PANEL_JSON_CHARS = int(os.getenv("AI_MAX_PANEL_JSON_CHARS", "3000"))

AGENT_DEMO_FAULTS = _parse_faults()
AGENT_LOG_RETENTION = int(os.getenv("AGENT_LOG_RETENTION", "5000"))

MYSQL_DSN = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"
