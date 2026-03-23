from __future__ import annotations

import os
import platform

from config import settings


def pytest_sessionstart(session):
    env_dir = os.path.join(os.getcwd(), settings.ALLURE_RESULTS_DIR)
    env_path = os.path.join(env_dir, "environment.properties")

    os.makedirs(env_dir, exist_ok=True)

    runner = (
        "Docker Compose (CI)"
        if os.getenv("GITHUB_ACTIONS") == "true"
        else "Docker Compose (Local)"
    )

    with open(env_path, "w", encoding="utf-8") as f:
        f.write(f"Python={platform.python_version()}\n")
        f.write(f"BaseURL={settings.BASE_URL}\n")
        f.write(f"DBPath={settings.DB_PATH}\n")
        f.write(f"Runner={runner}\n")
