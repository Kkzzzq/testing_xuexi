from __future__ import annotations

import config.settings as settings
import data.dashboards_data as data
from helpers.decorators import api_error_handler, retry
from services.http_client import HttpClient
from services.utils import total_log_in_method


class ApiDashboardsService:
    client = HttpClient(settings.GRAFANA_BASE_URL, auth=settings.BASIC_AUTH)

    @staticmethod
    @api_error_handler
    @retry(attempts=3)
    def create_folder(body: dict | None = None, auth: tuple[str, str] | None = None):
        response = ApiDashboardsService.client.request(
            "POST",
            "/api/folders",
            auth=auth or settings.BASIC_AUTH,
            json=body or data.body_for_create_folder,
            headers={"Content-Type": "application/json"},
        )
        total_log_in_method(response)
        return response, response.json().get("uid")

    @staticmethod
    @api_error_handler
    @retry(attempts=3)
    def create_dashboard(folder_uid: str, body: dict | None = None, auth: tuple[str, str] | None = None):
        response = ApiDashboardsService.client.request(
            "POST",
            "/api/dashboards/db",
            auth=auth or settings.BASIC_AUTH,
            json=body or data.get_body_for_create_dashboard(folder_uid),
            headers={"Content-Type": "application/json"},
        )
        total_log_in_method(response)
        return response, response.json().get("uid")

    @staticmethod
    @api_error_handler
    def get_dashboard_by_uid(uid: str, auth: tuple[str, str] | None = None):
        response = ApiDashboardsService.client.request("GET", f"/api/dashboards/uid/{uid}", auth=auth or settings.BASIC_AUTH)
        total_log_in_method(response)
        return response

    @staticmethod
    @api_error_handler
    def delete_dashboard_by_uid(uid: str, auth: tuple[str, str] | None = None):
        response = ApiDashboardsService.client.request("DELETE", f"/api/dashboards/uid/{uid}", auth=auth or settings.BASIC_AUTH)
        total_log_in_method(response)
        return response

    @staticmethod
    @api_error_handler
    def delete_folder(uid: str, auth: tuple[str, str] | None = None):
        response = ApiDashboardsService.client.request("DELETE", f"/api/folders/{uid}", auth=auth or settings.BASIC_AUTH)
        total_log_in_method(response)
        return response
