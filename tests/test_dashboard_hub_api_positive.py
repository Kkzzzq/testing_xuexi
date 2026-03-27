import allure
import pytest

from data.dashboard_hub_data import make_share_link_payload, make_subscription_payload
from services.dashboard_hub_service import DashboardHubService


@allure.title("Create subscription successfully")
@pytest.mark.PositiveDashboardHub
@pytest.mark.smoke
def test_create_subscription_success(session_context):
    payload = make_subscription_payload(
        session_context.dashboard_uid,
        session_context.existing_user_login,
        channel="email",
    )
    response, subscription_id = DashboardHubService.create_subscription(**payload)

    assert response.status_code == 201
    data = response.json()
    assert data["dashboard_uid"] == session_context.dashboard_uid
    assert data["user_login"] == session_context.existing_user_login

    session_context.register_subscription(subscription_id)


@allure.title("Create share link successfully")
@pytest.mark.PositiveDashboardHub
@pytest.mark.smoke
def test_create_share_link_success(session_context):
    payload = make_share_link_payload(session_context.dashboard_uid)
    response, token = DashboardHubService.create_share_link(**payload)

    assert response.status_code == 201
    data = response.json()
    assert data["dashboard_uid"] == session_context.dashboard_uid
    assert data["token"]

    session_context.register_share_token(token)


@allure.title("List subscriptions successfully")
@pytest.mark.PositiveDashboardHub
def test_get_subscriptions_success(session_context):
    create_payload = make_subscription_payload(
        session_context.dashboard_uid,
        session_context.existing_user_login,
        channel="slack",
    )
    create_response, subscription_id = DashboardHubService.create_subscription(**create_payload)
    assert create_response.status_code == 201

    session_context.register_subscription(subscription_id)

    response = DashboardHubService.list_subscriptions(session_context.dashboard_uid)
    assert response.status_code == 200

    payload = response.json()
    assert payload["dashboard_uid"] == session_context.dashboard_uid
    assert len(payload["items"]) >= 1
    assert any(item["id"] == subscription_id for item in payload["items"])


@allure.title("Read share link successfully")
@pytest.mark.PositiveDashboardHub
def test_get_share_link_success(session_context):
    create_payload = make_share_link_payload(session_context.dashboard_uid)
    create_response, token = DashboardHubService.create_share_link(**create_payload)
    assert create_response.status_code == 201

    session_context.register_share_token(token)

    response = DashboardHubService.get_share_link(token)
    assert response.status_code == 200

    payload = response.json()
    assert payload["dashboard_uid"] == session_context.dashboard_uid
    assert payload["token"] == token


@allure.title("Read dashboard AI summary successfully")
@pytest.mark.PositiveDashboardHub
def test_get_dashboard_summary_success(session_context):
    response = DashboardHubService.get_dashboard_summary(session_context.dashboard_uid)
    assert response.status_code == 200

    payload = response.json()
    assert payload["dashboard_uid"] == session_context.dashboard_uid
    assert payload["title"]
    assert payload["ai_summary"]
    assert payload["provider"]
    assert payload["model"]
    assert payload["prompt_version"]
    assert payload["source"] in {"ai", "fallback"}
