from __future__ import annotations

import logging

from data.organizations_data import make_organization_body
from data.users_credentials import (
    existing_credentials,
    low_access_credentials,
    organizations_user,
)
from services.api_dashboards_service import ApiDashboardsService
from services.api_organizations_service import ApiOrganizationsService
from services.api_users_service import ApiUsersService
from services.dashboard_hub_service import DashboardHubService
from services.db_service import DBService
from tests.context import TestContext


class ResourceManager:
    _context = TestContext()

    @staticmethod
    def _cleanup_user_if_exists(login: str) -> None:
        row = DBService.find_user_by_login(login)
        if row is None:
            return
        try:
            ApiUsersService.delete_api_user(userid=row[3])
        except Exception as exc:  # noqa: BLE001
            logging.warning("Failed to pre-delete user %s: %s", login, exc)

    @classmethod
    def prepare_environment(cls) -> TestContext:
        context = TestContext()

        for login in (
            existing_credentials["login"],
            low_access_credentials["login"],
            organizations_user["login"],
        ):
            cls._cleanup_user_if_exists(login)

        organization_body = make_organization_body()
        org_response, org_id = ApiOrganizationsService.create_new_organization(organization_body)
        if org_response.ok and org_id is not None:
            context.organizations.org_id = org_id
            context.organizations.org_name = organization_body["name"]

        folder_response, folder_uid = ApiDashboardsService.create_folder()
        if folder_response.ok and folder_uid:
            context.dashboards.folder_uid = folder_uid

        if context.dashboards.folder_uid:
            dashboard_response, dashboard_uid = ApiDashboardsService.create_dashboard(
                context.dashboards.folder_uid
            )
            if dashboard_response.ok and dashboard_uid:
                context.dashboards.dashboard_uid = dashboard_uid

        existing_response, existing_user_id = ApiUsersService.create_api_user(existing_credentials)
        if existing_response.ok and existing_user_id is not None:
            context.users.existing_user_id = existing_user_id
            context.users.existing_user_login = existing_credentials["login"]
            context.users.existing_user_email = existing_credentials["email"]

        low_response, low_user_id = ApiUsersService.create_api_user(low_access_credentials)
        if low_response.ok and low_user_id is not None:
            context.users.low_access_user_id = low_user_id
            context.users.low_access_user_login = low_access_credentials["login"]

        organizations_response, organizations_user_id = ApiUsersService.create_api_user(
            organizations_user
        )
        if organizations_response.ok and organizations_user_id is not None:
            context.users.organizations_user_id = organizations_user_id

        cls._context = context
        return context

    @classmethod
    def get_context(cls) -> TestContext:
        if not cls._context.dashboards.dashboard_uid:
            cls.prepare_environment()
        return cls._context

    @classmethod
    def cleanup_environment(cls) -> None:
        context = cls._context

        if context.dashboard_hub.subscription_id:
            try:
                DashboardHubService.delete_subscription(context.dashboard_hub.subscription_id)
            except Exception as exc:  # noqa: BLE001
                logging.warning("Failed to delete subscription %s: %s", context.dashboard_hub.subscription_id, exc)

        if context.dashboards.dashboard_uid:
            try:
                ApiDashboardsService.delete_dashboard_by_uid(context.dashboards.dashboard_uid)
            except Exception as exc:  # noqa: BLE001
                logging.warning("Failed to delete dashboard %s: %s", context.dashboards.dashboard_uid, exc)

        if context.dashboards.folder_uid:
            try:
                ApiDashboardsService.delete_folder(context.dashboards.folder_uid)
            except Exception as exc:  # noqa: BLE001
                logging.warning("Failed to delete folder %s: %s", context.dashboards.folder_uid, exc)

        for user_id in (
            context.users.organizations_user_id,
            context.users.low_access_user_id,
            context.users.existing_user_id,
        ):
            if not user_id:
                continue
            try:
                ApiUsersService.delete_api_user(userid=user_id)
            except Exception as exc:  # noqa: BLE001
                logging.warning("Failed to delete user %s: %s", user_id, exc)

        if context.organizations.org_id:
            try:
                ApiOrganizationsService.delete_organization(context.organizations.org_id)
            except Exception as exc:  # noqa: BLE001
                logging.warning("Failed to delete org %s: %s", context.organizations.org_id, exc)

        cls._context = TestContext()
