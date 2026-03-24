from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

ALLURE_RESULTS_DIR = os.getenv("ALLURE_RESULTS_DIR", "allure-results")

# Grafana
GRAFANA_BASE_URL = os.getenv("GRAFANA_BASE_URL", "http://grafana:3000")
BASE_URL = GRAFANA_BASE_URL  # backward compatibility
GRAFANA_ADMIN_USER = os.getenv("GRAFANA_ADMIN_USER", "admin")
GRAFANA_ADMIN_PASSWORD = os.getenv("GRAFANA_ADMIN_PASSWORD", "admin")
BASIC_AUTH = (GRAFANA_ADMIN_USER, GRAFANA_ADMIN_PASSWORD)

GRAFANA_LOW_ACCESS_USER = os.getenv("GRAFANA_LOW_ACCESS_USER", "LowAccess")
GRAFANA_LOW_ACCESS_PASSWORD = os.getenv("GRAFANA_LOW_ACCESS_PASSWORD", "test")
LOW_ACCESS = (GRAFANA_LOW_ACCESS_USER, GRAFANA_LOW_ACCESS_PASSWORD)

DB_PATH = os.getenv("DB_PATH", "/var/lib/grafana/grafana.db")

# Dashboard Hub
DASHBOARD_HUB_BASE_URL = os.getenv("DASHBOARD_HUB_BASE_URL", "http://dashboard-hub:8000")

# MySQL
MYSQL_HOST = os.getenv("MYSQL_HOST", "mysql")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "app")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "app")
MYSQL_DB = os.getenv("MYSQL_DB", "dashboard_hub")

# Redis
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
