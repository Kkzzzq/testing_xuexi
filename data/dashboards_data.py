from __future__ import annotations

import time


body_for_create_folder = {
    "title": f"folder-auto-{int(time.time())}"
}


def get_body_for_create_dashboard(folder_uid: str) -> dict:
    suffix = int(time.time() * 1000)
    return {
        "dashboard": {
            "id": None,
            "uid": None,
            "title": f"dashboard-auto-{suffix}",
            "timezone": "browser",
            "schemaVersion": 39,
            "version": 0,
            "refresh": "25s",
            "panels": [],
            "tags": ["automation", "dashboard-hub"],
        },
        "folderUid": folder_uid,
        "overwrite": False,
        "message": "create dashboard from api automation",
    }
