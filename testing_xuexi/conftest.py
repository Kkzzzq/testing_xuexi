from __future__ import annotations

from pathlib import Path

import config.settings as settings


def pytest_sessionstart(session):
    results_dir = Path(settings.ALLURE_RESULTS_DIR)
    results_dir.mkdir(parents=True, exist_ok=True)

    env_lines = [
        f"GRAFANA_BASE_URL={settings.GRAFANA_BASE_URL}",
        f"DASHBOARD_HUB_BASE_URL={settings.DASHBOARD_HUB_BASE_URL}",
        f"MYSQL_HOST={settings.MYSQL_HOST}",
        f"REDIS_HOST={settings.REDIS_HOST}",
        "STACK=Grafana + Dashboard Hub + MySQL + Redis + Prometheus",
    ]
    (results_dir / "environment.properties").write_text("\n".join(env_lines), encoding="utf-8")
