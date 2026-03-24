import allure
import pytest

from data.dashboard_hub_data import make_share_link_payload, make_subscription_payload
from services.dashboard_hub_service import DashboardHubService


@allure.title("Create subscription successfully")
@pytest.mark.PositiveDashboardHub
@pytest.mark.smoke
def test_create_subscription_success(session_context):
    payload = make_subscription_payload(session_context.dashboard_uid, session_context.existing_user_login)
    response = DashboardHubService.create_subscription(payload)
    assert response.status_code == 201
    data = response.json()
    assert data["dashboard_uid"] == session_context.dashboard_uid
    assert data["user_login"] == session_context.existing_user_login
    session_context.subscription_id = data["id"]


@allure.title("Create share link successfully")
@pytest.mark.PositiveDashboardHub
@pytest.mark.smoke
def test_create_share_link_success(session_context):
    payload = make_share_link_payload(session_context.dashboard_uid)
    response = DashboardHubService.create_share_link(payload)
    assert response.status_code == 201
    data = response.json()
    assert data["dashboard_uid"] == session_context.dashboard_uid
    assert data["token"]
    session_context.share_token = data["token"]


@allure.title("List subscriptions successfully")
@pytest.mark.PositiveDashboardHub
def test_get_subscriptions_success(session_context):
    if not session_context.subscription_id:
        create_response = DashboardHubService.create_subscription(
            make_subscription_payload(session_context.dashboard_uid, session_context.existing_user_login)
        )
        session_context.subscription_id = create_response.json()["id"]

    response = DashboardHubService.get_subscriptions(session_context.dashboard_uid)
    assert response.status_code == 200
    payload = response.json()
    assert payload["dashboard_uid"] == session_context.dashboard_uid
    assert len(payload["items"]) >= 1


@allure.title("Read share link successfully")
@pytest.mark.PositiveDashboardHub
def test_get_share_link_success(session_context):
    if not session_context.share_token:
        create_response = DashboardHubService.create_share_link(make_share_link_payload(session_context.dashboard_uid))
        session_context.share_token = create_response.json()["token"]

    response = DashboardHubService.get_share_link(session_context.share_token)
    assert response.status_code == 200
    payload = response.json()
    assert payload["dashboard_uid"] == session_context.dashboard_uid
    assert payload["token"] == session_context.share_token


@allure.title("Read dashboard summary successfully")
@pytest.mark.PositiveDashboardHub
def test_get_dashboard_summary_success(session_context):
    response = DashboardHubService.get_dashboard_summary(session_context.dashboard_uid)
    assert response.status_code == 200
    payload = response.json()
    assert payload["dashboard_uid"] == session_context.dashboard_uid
    assert payload["title"]
