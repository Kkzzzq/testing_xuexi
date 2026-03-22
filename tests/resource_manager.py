from __future__ import annotations

import logging
import os
import shutil

from config import settings
from data.organizations_data import make_test_organization_body
from data.users_credentials import (
    existing_credentials,
    low_access_credentials,
    organizations_user,
)
from helpers.schemas.organizations_schema import CreateOrganizationSchema
from services.api_dashboards_service import ApiDashboardsService
from services.api_organizations_service import ApiOrganizationsService
from services.api_users_service import ApiUsersService
from services.utils import validate_status_code_and_body
from tests.context import TestContext

RUNTIME_DATA_FILES = (
    (settings.USERS_TEMPLATE_PATH, settings.USERS_PATH, "users.json"),
    (settings.DASHBOARDS_TEMPLATE_PATH, settings.DASHBOARDS_PATH, "dashboards.json"),
    (settings.ORGANIZATIONS_TEMPLATE_PATH, settings.ORGANIZATIONS_PATH, "organizations.json"),
)


def ensure_runtime_data_files() -> None:
    os.makedirs(settings.DATA_DIR, exist_ok=True)

    for template_path, target_path, display_name in RUNTIME_DATA_FILES:
        if not os.path.exists(target_path):
            shutil.copy(template_path, target_path)
            logging.info("Created %s from template", display_name)
        else:
            logging.info("%s already exists, skip template copy", display_name)


def _delete_user_by_login_if_exists(login: str) -> None:
    try:
        user_id = ApiUsersService.find_user_by_login(login)
        if user_id:
            ApiUsersService.delete_api_user(user_id)
            logging.info("Deleted leftover user before setup: %s (id=%s)", login, user_id)
    except Exception as exc:
        logging.warning("Failed to delete leftover user %s before setup: %s", login, exc)


def _cleanup_known_users_before_setup() -> None:
    for login in [
        low_access_credentials["login"],
        organizations_user["login"],
        existing_credentials["login"],
    ]:
        _delete_user_by_login_if_exists(login)


def prepare_session_resources(test_context: TestContext) -> TestContext:
    ensure_runtime_data_files()
    _cleanup_known_users_before_setup()

    try:
        organization_body = make_test_organization_body()
        response, org_id = ApiOrganizationsService.create_new_organization(body=organization_body)
        validate_status_code_and_body(response, CreateOrganizationSchema, 200)
        test_context.organizations.org_id = int(org_id)
        test_context.organizations.org_name = organization_body["name"]

        response, folder_uid = ApiDashboardsService.create_folder()
        assert response.status_code == 200, f"Create folder failed: {response.text}"
        test_context.dashboards.folder_uid = folder_uid

        response, dashboard_uid = ApiDashboardsService.create_dashboard(folder_uid=folder_uid)
        assert response.status_code == 200, f"Create dashboard failed: {response.text}"
        test_context.dashboards.dashboard_uid = dashboard_uid

        response, low_access_user_id = ApiUsersService.create_api_user(low_access_credentials)
        assert response.status_code == 200, f"Create low-access user failed: {response.text}"
        test_context.users.low_access_user_id = low_access_user_id

        try:
            ApiOrganizationsService.delete_user_from_org(userid=low_access_user_id)
        except Exception as exc:
            logging.warning(
                "Failed to remove low-access user %s from default org: %s",
                low_access_user_id,
                exc,
            )

        response, org_user_id = ApiUsersService.create_api_user(organizations_user)
        assert response.status_code == 200, f"Create organization user failed: {response.text}"
        test_context.users.organizations_user_id = org_user_id

        response, existing_user_id = ApiUsersService.create_api_user(existing_credentials)
        assert response.status_code == 200, f"Create existing user failed: {response.text}"
        test_context.users.existing_user_id = existing_user_id

        return test_context

    except Exception:
        safe_cleanup(test_context)
        raise


def safe_cleanup(test_context: TestContext) -> None:
    for user_id in [
        test_context.users.existing_user_id,
        test_context.users.low_access_user_id,
        test_context.users.organizations_user_id,
    ]:
        try:
            if user_id:
                ApiUsersService.delete_api_user(user_id)
        except Exception as exc:
            logging.warning("Cleanup user %s failed: %s", user_id, exc)

    try:
        if test_context.dashboards.dashboard_uid:
            ApiDashboardsService.delete_dashboard(test_context.dashboards.dashboard_uid)
    except Exception as exc:
        logging.warning("Cleanup dashboard failed: %s", exc)

    try:
        if test_context.dashboards.folder_uid:
            ApiDashboardsService.delete_folder_for_dashboard(
                test_context.dashboards.folder_uid
            )
    except Exception as exc:
        logging.warning("Cleanup folder failed: %s", exc)

    try:
        if test_context.organizations.org_id:
            ApiOrganizationsService.delete_organization(
                test_context.organizations.org_id
            )
    except Exception as exc:
        logging.warning("Cleanup organization failed: %s", exc)
