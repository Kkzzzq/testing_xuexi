from __future__ import annotations

from datetime import datetime

from requests import Response

import config.settings as settings
from helpers.decorators import api_error_handler
from services.http_client import HttpClient
from services.utils import safe_json, total_log_in_method


class DashboardHubService:
    client = HttpClient(settings.DASHBOARD_HUB_BASE_URL)

    @staticmethod
    def _merge_headers(replay_id: str | None, headers: dict[str, str] | None = None) -> dict[str, str]:
        merged = dict(headers or {})
        if replay_id:
            merged["X-Agent-Replay-Id"] = replay_id
        return merged

    @staticmethod
    @api_error_handler
    def create_subscription(
        dashboard_uid: str,
        user_login: str,
        channel: str = "email",
        cron: str = "0 */6 * * *",
        replay_id: str | None = None,
    ) -> tuple[Response, int | None]:
        response = DashboardHubService.client.request(
            "POST",
            "/api/v1/subscriptions",
            json={
                "dashboard_uid": dashboard_uid,
                "user_login": user_login,
                "channel": channel,
                "cron": cron,
            },
            headers=DashboardHubService._merge_headers(replay_id, {"Content-Type": "application/json"}),
        )
        total_log_in_method(response)
        return response, safe_json(response).get("id")

    @staticmethod
    @api_error_handler
    def list_subscriptions(dashboard_uid: str, replay_id: str | None = None) -> Response:
        response = DashboardHubService.client.request(
            "GET",
            f"/api/v1/dashboards/{dashboard_uid}/subscriptions",
            headers=DashboardHubService._merge_headers(replay_id),
        )
        total_log_in_method(response)
        return response

    @staticmethod
    @api_error_handler
    def delete_subscription(subscription_id: int, replay_id: str | None = None) -> Response:
        response = DashboardHubService.client.request(
            "DELETE",
            f"/api/v1/subscriptions/{subscription_id}",
            headers=DashboardHubService._merge_headers(replay_id),
        )
        total_log_in_method(response)
        return response

    @staticmethod
    @api_error_handler
    def create_share_link(
        dashboard_uid: str,
        expire_at: datetime | str | None = None,
        replay_id: str | None = None,
    ) -> tuple[Response, str | None]:
        expire_value = expire_at.isoformat() if isinstance(expire_at, datetime) else expire_at
        response = DashboardHubService.client.request(
            "POST",
            "/api/v1/share-links",
            json={"dashboard_uid": dashboard_uid, "expire_at": expire_value},
            headers=DashboardHubService._merge_headers(replay_id, {"Content-Type": "application/json"}),
        )
        total_log_in_method(response)
        return response, safe_json(response).get("token")

    @staticmethod
    @api_error_handler
    def get_share_link(token: str, replay_id: str | None = None) -> Response:
        response = DashboardHubService.client.request(
            "GET",
            f"/api/v1/share-links/{token}",
            headers=DashboardHubService._merge_headers(replay_id),
        )
        total_log_in_method(response)
        return response

    @staticmethod
    @api_error_handler
    def delete_share_link(token: str, replay_id: str | None = None) -> Response:
        response = DashboardHubService.client.request(
            "DELETE",
            f"/api/v1/share-links/{token}",
            headers=DashboardHubService._merge_headers(replay_id),
        )
        total_log_in_method(response)
        return response

    @staticmethod
    @api_error_handler
    def get_dashboard_summary(dashboard_uid: str, replay_id: str | None = None) -> Response:
        response = DashboardHubService.client.request(
            "GET",
            f"/api/v1/dashboards/{dashboard_uid}/summary",
            headers=DashboardHubService._merge_headers(replay_id),
        )
        total_log_in_method(response)
        return response

    @staticmethod
    @api_error_handler
    def get_agent_logs(replay_id: str, limit: int = 200) -> Response:
        response = DashboardHubService.client.request(
            "GET",
            "/agent/logs",
            params={"replay_id": replay_id, "limit": limit},
        )
        total_log_in_method(response)
        return response
