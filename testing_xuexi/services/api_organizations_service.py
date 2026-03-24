from __future__ import annotations

import config.settings as settings
from data.organizations_data import make_add_user_body, make_organization_body
from helpers.decorators import api_error_handler, retry
from services.http_client import HttpClient
from services.utils import total_log_in_method


class ApiOrganizationsService:
    client = HttpClient(settings.GRAFANA_BASE_URL, auth=settings.BASIC_AUTH)

    @staticmethod
    @api_error_handler
    @retry(attempts=3)
    def create_new_organization(body: dict | None = None, auth: tuple[str, str] | None = None):
        response = ApiOrganizationsService.client.request(
            "POST",
            "/api/orgs",
            auth=auth or settings.BASIC_AUTH,
            json=body or make_organization_body(),
            headers={"Content-Type": "application/json"},
        )
        total_log_in_method(response)
        return response, response.json().get("orgId")

    @staticmethod
    @api_error_handler
    def add_user_to_organization(org_id: int, login_or_email: str, role: str = "Viewer", auth: tuple[str, str] | None = None):
        response = ApiOrganizationsService.client.request(
            "POST",
            f"/api/orgs/{org_id}/users",
            auth=auth or settings.BASIC_AUTH,
            json=make_add_user_body(login_or_email, role),
            headers={"Content-Type": "application/json"},
        )
        total_log_in_method(response)
        return response

    @staticmethod
    @api_error_handler
    def delete_organization(org_id: int, auth: tuple[str, str] | None = None):
        response = ApiOrganizationsService.client.request("DELETE", f"/api/orgs/{org_id}", auth=auth or settings.BASIC_AUTH)
        total_log_in_method(response)
        return response
