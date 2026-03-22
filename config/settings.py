from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(
    os.getenv(
        "GITHUB_WORKSPACE",
        str(Path(__file__).resolve().parent.parent),
    )
)

DATA_DIR = BASE_DIR / "data"

DEFAULT_DB_PATH = "/var/lib/grafana/grafana.db"

DB_PATH = os.getenv("GRAFANA_DB_PATH", DEFAULT_DB_PATH)
BASE_URL = os.getenv("GRAFANA_BASE_URL", "http://localhost:3000")

GRAFANA_ADMIN_USER = os.getenv("GRAFANA_ADMIN_USER", "admin")
GRAFANA_ADMIN_PASSWORD = os.getenv("GRAFANA_ADMIN_PASSWORD", "admin")
BASIC_AUTH = (GRAFANA_ADMIN_USER, GRAFANA_ADMIN_PASSWORD)

GRAFANA_LOW_ACCESS_USER = os.getenv("GRAFANA_LOW_ACCESS_USER", "LowAccess")
GRAFANA_LOW_ACCESS_PASSWORD = os.getenv("GRAFANA_LOW_ACCESS_PASSWORD", "test")
LOW_ACCESS = (GRAFANA_LOW_ACCESS_USER, GRAFANA_LOW_ACCESS_PASSWORD)

USERS_PATH = str(DATA_DIR / "users.json")
DASHBOARDS_PATH = str(DATA_DIR / "dashboards.json")
ORGANIZATIONS_PATH = str(DATA_DIR / "organizations.json")

USERS_TEMPLATE_PATH = str(DATA_DIR / "users.template.json")
DASHBOARDS_TEMPLATE_PATH = str(DATA_DIR / "dashboards.template.json")
ORGANIZATIONS_TEMPLATE_PATH = str(DATA_DIR / "organizations.template.json")

ALLURE_RESULTS_DIR = "allure-results"
