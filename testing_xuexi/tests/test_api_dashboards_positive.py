import allure
import pytest

from helpers.schemas.dashboards_schema import CreateDashboardStatus, CreateFolderResponse
from services.api_dashboards_service import ApiDashboardsService
from services.utils import validate_schema


@allure.title("Create folder and validate response schema")
@pytest.mark.PositiveApi
@pytest.mark.smoke
def test_create_folder_schema():
    response, folder_uid = ApiDashboardsService.create_folder()
    assert response.status_code == 200
    payload = validate_schema(CreateFolderResponse, response.json())
    assert payload.uid == folder_uid
    ApiDashboardsService.delete_folder(folder_uid)


@allure.title("Create dashboard and validate response schema")
@pytest.mark.PositiveApi
@pytest.mark.regression
def test_create_dashboard_schema():
    folder_response, folder_uid = ApiDashboardsService.create_folder()
    assert folder_response.status_code == 200

    response, dashboard_uid = ApiDashboardsService.create_dashboard(folder_uid)
    assert response.status_code == 200
    payload = validate_schema(CreateDashboardStatus, response.json())
    assert payload.uid == dashboard_uid

    ApiDashboardsService.delete_dashboard_by_uid(dashboard_uid)
    ApiDashboardsService.delete_folder(folder_uid)
