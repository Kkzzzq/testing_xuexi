from __future__ import annotations

import config.settings as settings
from helpers.decorators import api_error_handler, retry
from services.http_client import HttpClient
from services.utils import total_log_in_method


class DashboardHubService:
    client = HttpClient(settings.DASHBOARD_HUB_BASE_URL)

    @staticmethod
    @api_error_handler
    @retry(attempts=3)
    def create_subscription(payload: dict):
        response = DashboardHubService.client.request("POST", "/api/v1/subscriptions", json=payload)
        total_log_in_method(response)
        return response

    @staticmethod
    @api_error_handler
    def get_subscriptions(dashboard_uid: str):
        response = DashboardHubService.client.request("GET", f"/api/v1/dashboards/{dashboard_uid}/subscriptions")
        total_log_in_method(response)
        return response

    @staticmethod
    @api_error_handler
    def delete_subscription(subscription_id: int):
        response = DashboardHubService.client.request("DELETE", f"/api/v1/subscriptions/{subscription_id}")
        total_log_in_method(response)
        return response

    @staticmethod
    @api_error_handler
    def create_share_link(payload: dict):
        response = DashboardHubService.client.request("POST", "/api/v1/share-links", json=payload)
        total_log_in_method(response)
        return response

    @staticmethod
    @api_error_handler
    def get_share_link(token: str):
        response = DashboardHubService.client.request("GET", f"/api/v1/share-links/{token}")
        total_log_in_method(response)
        return response

    @staticmethod
    @api_error_handler
    def get_dashboard_summary(dashboard_uid: str):
        response = DashboardHubService.client.request("GET", f"/api/v1/dashboards/{dashboard_uid}/summary")
        total_log_in_method(response)
        return response
