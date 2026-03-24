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
    def _extract_user_id(row) -> int | None:
        if row is None:
            return None

        if isinstance(row, dict):
            for key in ("id", "user_id"):
                value = row.get(key)
                if isinstance(value, int):
                    return value
            return None

        if hasattr(row, "id") and isinstance(getattr(row, "id"), int):
            return getattr(row, "id")

        if isinstance(row, (tuple, list)):
            if len(row) > 3 and isinstance(row[3], int):
                return row[3]
            if len(row) > 0 and isinstance(row[0], int):
                return row[0]

        return None

    @staticmethod
    def _require_created(ok: bool, value, resource_name: str):
        if ok and value is not None:
            return value
        raise RuntimeError(f"Failed to create required resource: {resource_name}")

    @staticmethod
    def _cleanup_user_if_exists(login: str) -> None:
        row = DBService.find_user_by_login(login)
        user_id = ResourceManager._extract_user_id(row)
        if user_id is None:
            return

        try:
            ApiUsersService.delete_api_user(userid=user_id)
        except Exception as exc:  # noqa: BLE001
            logging.warning("Failed to pre-delete user %s: %s", login, exc)

    @classmethod
    def prepare_environment(cls) -> TestContext:
        context = TestContext()
        cls._context = context

        try:
            for login in (
                existing_credentials["login"],
                low_access_credentials["login"],
                organizations_user["login"],
            ):
                cls._cleanup_user_if_exists(login)

            organization_body = make_organization_body()
            org_response, org_id = ApiOrganizationsService.create_new_organization(
                organization_body
            )
            context.organizations.org_id = cls._require_created(
                org_response.ok,
                org_id,
                "organization",
            )
            context.organizations.org_name = organization_body["name"]

            folder_response, folder_uid = ApiDashboardsService.create_folder()
            context.dashboards.folder_uid = cls._require_created(
                folder_response.ok,
                folder_uid,
                "folder",
            )

            dashboard_response, dashboard_uid = ApiDashboardsService.create_dashboard(
                context.dashboards.folder_uid
            )
            context.dashboards.dashboard_uid = cls._require_created(
                dashboard_response.ok,
                dashboard_uid,
                "dashboard",
            )

            existing_response, existing_user_id = ApiUsersService.create_api_user(
                existing_credentials
            )
            context.users.existing_user_id = cls._require_created(
                existing_response.ok,
                existing_user_id,
                "existing user",
            )
            context.users.existing_user_login = existing_credentials["login"]
            context.users.existing_user_email = existing_credentials["email"]

            low_response, low_user_id = ApiUsersService.create_api_user(
                low_access_credentials
            )
            context.users.low_access_user_id = cls._require_created(
                low_response.ok,
                low_user_id,
                "low access user",
            )
            context.users.low_access_user_login = low_access_credentials["login"]

            organizations_response, organizations_user_id = ApiUsersService.create_api_user(
                organizations_user
            )
            context.users.organizations_user_id = cls._require_created(
                organizations_response.ok,
                organizations_user_id,
                "organizations user",
            )

            cls._context = context
            return context

        except Exception:
            cls._context = context
            try:
                cls.cleanup_environment()
            finally:
                raise

    @classmethod
    def get_context(cls) -> TestContext:
        context = cls._context
        required_values = (
            context.organizations.org_id,
            context.dashboards.folder_uid,
            context.dashboards.dashboard_uid,
            context.users.existing_user_id,
            context.users.low_access_user_id,
            context.users.organizations_user_id,
        )

        if not all(required_values):
            return cls.prepare_environment()

        return context

    @classmethod
    def cleanup_environment(cls) -> None:
        context = cls._context

        if context.dashboard_hub.share_token:
            try:
                DashboardHubService.delete_share_link(context.dashboard_hub.share_token)
            except Exception as exc:  # noqa: BLE001
                logging.warning(
                    "Failed to delete share link %s: %s",
                    context.dashboard_hub.share_token,
                    exc,
                )

        if context.dashboard_hub.subscription_id:
            try:
                DashboardHubService.delete_subscription(context.dashboard_hub.subscription_id)
            except Exception as exc:  # noqa: BLE001
                logging.warning(
                    "Failed to delete subscription %s: %s",
                    context.dashboard_hub.subscription_id,
                    exc,
                )

        if context.dashboards.dashboard_uid:
            try:
                ApiDashboardsService.delete_dashboard_by_uid(context.dashboards.dashboard_uid)
            except Exception as exc:  # noqa: BLE001
                logging.warning(
                    "Failed to delete dashboard %s: %s",
                    context.dashboards.dashboard_uid,
                    exc,
                )

        if context.dashboards.folder_uid:
            try:
                ApiDashboardsService.delete_folder(context.dashboards.folder_uid)
            except Exception as exc:  # noqa: BLE001
                logging.warning(
                    "Failed to delete folder %s: %s",
                    context.dashboards.folder_uid,
                    exc,
                )

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
                logging.warning(
                    "Failed to delete org %s: %s",
                    context.organizations.org_id,
                    exc,
                )

        cls._context = TestContext()
