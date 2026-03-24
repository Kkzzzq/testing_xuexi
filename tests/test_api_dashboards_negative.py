from __future__ import annotations

import allure
import pytest

from config import settings
from helpers.schemas.dashboards_schema import GetDashboardsWithIncorrectCredentialsSchema
from helpers.schemas.user_schema import Get404DashboardSchema
from services.api_dashboards_service import ApiDashboardsService
from services.utils import assert_json_response, validate_status_code_and_body

pytestmark = pytest.mark.usefixtures("session_resources")

BAD_AUTH_CASES = [
    pytest.param(("wrong-admin", "wrong-password"), id="wrong-user-and-password"),
    pytest.param((settings.BASIC_AUTH[0], "wrong-password"), id="wrong-password"),
    pytest.param(("wrong-user", settings.BASIC_AUTH[1]), id="wrong-user"),
]

BAD_UID_SUFFIXES = [
    pytest.param("-404", id="suffix-404"),
    pytest.param("-missing", id="suffix-missing"),
]


@allure.title("Test get dashboard with incorrect auth")
@allure.description("This test attempts to get dashboard with invalid basic auth")
@allure.tag("ApiDashboardsService", "Negative")
@allure.id("get_dashboard_with_incorrect_auth")
@pytest.mark.NegativeApi
@pytest.mark.parametrize("auth", BAD_AUTH_CASES)
def test_get_dashboard_with_incorrect_auth(auth, test_context):
    response = ApiDashboardsService.get_dashboard(
        dashboard_uid=test_context.dashboards.dashboard_uid,
        auth=auth,
    )
    validate_status_code_and_body(response, GetDashboardsWithIncorrectCredentialsSchema, 401)
    assert_json_response(response)


@allure.title("Test get 404 dashboard")
@allure.description("This test attempts to get non-existing dashboard by uid")
@allure.tag("ApiDashboardsService", "Negative")
@allure.id("get_404_dashboard")
@pytest.mark.NegativeApi
@pytest.mark.parametrize("suffix", BAD_UID_SUFFIXES)
def test_get_404_dashboard(suffix, test_context):
    invalid_uid = f"{test_context.dashboards.dashboard_uid}{suffix}"
    response = ApiDashboardsService.get_dashboard(dashboard_uid=invalid_uid)
    validate_status_code_and_body(response, Get404DashboardSchema, 404)
    assert_json_response(response)
