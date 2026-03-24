from __future__ import annotations

from requests import Response

import config.settings as settings
from data.users_credentials import change_password
from helpers.decorators import api_error_handler, retry
from services.http_client import HttpClient
from services.utils import total_log_in_method


class ApiUsersService:
    client = HttpClient(settings.GRAFANA_BASE_URL, auth=settings.BASIC_AUTH)

    @staticmethod
    @api_error_handler
    @retry(attempts=3)
    def create_api_user(credentials: dict, auth: tuple[str, str] | None = None) -> tuple[Response, int | None]:
        response = ApiUsersService.client.request(
            "POST",
            "/api/admin/users",
            auth=auth or settings.BASIC_AUTH,
            json=credentials,
            headers={"Content-Type": "application/json"},
        )
        total_log_in_method(response)
        return response, response.json().get("id")

    @staticmethod
    @api_error_handler
    def delete_api_user(user_id: int, auth: tuple[str, str] | None = None) -> Response:
        response = ApiUsersService.client.request("DELETE", f"/api/admin/users/{user_id}", auth=auth or settings.BASIC_AUTH)
        total_log_in_method(response)
        return response

    @staticmethod
    @api_error_handler
    def change_user_password(auth: tuple[str, str] | None = None, body: dict | None = None) -> Response:
        response = ApiUsersService.client.request(
            "PUT",
            "/api/user/password",
            auth=auth or settings.BASIC_AUTH,
            json=body or change_password,
            headers={"Content-Type": "application/json"},
        )
        total_log_in_method(response)
        return response
