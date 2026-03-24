from __future__ import annotations

from data.organizations_data import make_organization_body
from data.users_credentials import make_user_credentials
from services.api_dashboards_service import ApiDashboardsService
from services.api_organizations_service import ApiOrganizationsService
from services.api_users_service import ApiUsersService
from tests.context import TestContext


class ResourceManager:
    _context = TestContext()

    @classmethod
    def prepare_environment(cls) -> TestContext:
        context = TestContext()

        org_response, org_id = ApiOrganizationsService.create_new_organization(make_organization_body())
        if org_response.ok:
            context.org_id = org_id

        folder_response, folder_uid = ApiDashboardsService.create_folder()
        if folder_response.ok:
            context.folder_uid = folder_uid

        if context.folder_uid:
            dashboard_response, dashboard_uid = ApiDashboardsService.create_dashboard(context.folder_uid)
            if dashboard_response.ok:
                context.dashboard_uid = dashboard_uid

        existing_user = make_user_credentials("existing_user")
        existing_response, existing_user_id = ApiUsersService.create_api_user(existing_user)
        if existing_response.ok:
            context.existing_user_id = existing_user_id
            context.existing_user_login = existing_user["login"]
            context.existing_user_email = existing_user["email"]

        low_user = make_user_credentials("low_access_user")
        low_user["login"] = "LowAccess"
        low_user["email"] = "low_access_user@example.com"
        low_user["password"] = "test"
        low_response, low_id = ApiUsersService.create_api_user(low_user)
        if low_response.ok:
            context.low_access_user_id = low_id
            context.low_access_user_login = low_user["login"]

        cls._context = context
        return context

    @classmethod
    def get_context(cls) -> TestContext:
        if not cls._context.dashboard_uid:
            cls.prepare_environment()
        return cls._context

    @classmethod
    def cleanup_environment(cls):
        context = cls._context
        if context.dashboard_uid:
            ApiDashboardsService.delete_dashboard_by_uid(context.dashboard_uid)
        if context.folder_uid:
            ApiDashboardsService.delete_folder(context.folder_uid)
        if context.existing_user_id:
            ApiUsersService.delete_api_user(context.existing_user_id)
        if context.low_access_user_id:
            ApiUsersService.delete_api_user(context.low_access_user_id)
        if context.org_id:
            ApiOrganizationsService.delete_organization(context.org_id)
        cls._context = TestContext()
