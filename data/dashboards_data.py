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
            "tags": ["automation", "dashboard-hub", "ai-summary"],
            "panels": [
                {
                    "id": 1,
                    "type": "text",
                    "title": "CPU Usage Overview",
                    "description": "展示 CPU 使用率、平均值、峰值与变化趋势。",
                    "gridPos": {"h": 8, "w": 8, "x": 0, "y": 0},
                    "options": {
                        "mode": "markdown",
                        "content": (
                            "### CPU Usage\n"
                            "- current: 72%\n"
                            "- avg_1h: 61%\n"
                            "- peak_1h: 89%\n"
                            "- trend: rising\n"
                            "- note: 最近 30 分钟计算压力上升"
                        ),
                    },
                },
                {
                    "id": 2,
                    "type": "text",
                    "title": "Memory Usage Overview",
                    "description": "展示内存当前值、平均值和波动情况。",
                    "gridPos": {"h": 8, "w": 8, "x": 8, "y": 0},
                    "options": {
                        "mode": "markdown",
                        "content": (
                            "### Memory Usage\n"
                            "- current: 64%\n"
                            "- avg_1h: 60%\n"
                            "- peak_1h: 71%\n"
                            "- trend: stable\n"
                            "- note: 内存整体平稳，没有明显突增"
                        ),
                    },
                },
                {
                    "id": 3,
                    "type": "text",
                    "title": "System Load Overview",
                    "description": "展示系统负载、最近变化趋势和告警倾向。",
                    "gridPos": {"h": 8, "w": 8, "x": 16, "y": 0},
                    "options": {
                        "mode": "markdown",
                        "content": (
                            "### System Load\n"
                            "- current: 5.2\n"
                            "- avg_1h: 4.1\n"
                            "- peak_1h: 6.3\n"
                            "- trend: rising\n"
                            "- note: 高峰时段负载抬升明显"
                        ),
                    },
                },
            ],
        },
        "folderUid": folder_uid,
        "overwrite": False,
        "message": "create dashboard from api automation",
    }
