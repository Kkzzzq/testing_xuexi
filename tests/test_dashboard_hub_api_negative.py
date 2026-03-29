import allure
import pytest

from data.dashboard_hub_data import make_share_link_payload
from services.dashboard_hub_service import DashboardHubService


@allure.label("fault_scenario", "subscription_unknown_dashboard")
@pytest.mark.NegativeDashboardHub
def test_create_subscription_with_unknown_dashboard():
    response, _ = DashboardHubService.create_subscription(
        dashboard_uid="not-exists-uid",
        user_login="nobody",
        channel="email",
        cron="0 */6 * * *",
    )
    assert response.status_code == 404


@allure.label("fault_scenario", "subscription_conflict")
@pytest.mark.NegativeDashboardHub
def test_create_duplicate_subscription(session_context):
    payload = {
        "dashboard_uid": session_context.dashboard_uid,
        "user_login": session_context.existing_user_login,
        "channel": "webhook",
        "cron": "0 */6 * * *",
    }

    first, first_id = DashboardHubService.create_subscription(**payload)
    assert first.status_code == 201
    session_context.register_subscription(first_id)

    second, _ = DashboardHubService.create_subscription(**payload)
    assert second.status_code == 409


@allure.label("fault_scenario", "share_link_unknown_token")
@pytest.mark.NegativeDashboardHub
def test_get_unknown_share_token():
    response = DashboardHubService.get_share_link("missing-token")
    assert response.status_code == 404


@allure.label("fault_scenario", "subscription_invalid_channel")
@pytest.mark.NegativeDashboardHub
def test_create_subscription_with_illegal_channel(session_context):
    response, _ = DashboardHubService.create_subscription(
        dashboard_uid=session_context.dashboard_uid,
        user_login=session_context.low_access_user_login,
        channel="sms",
        cron="0 */6 * * *",
    )
    assert response.status_code == 422


@allure.label("fault_scenario", "share_link_expired_read")
@pytest.mark.NegativeDashboardHub
def test_get_expired_share_link(session_context):
    payload = make_share_link_payload(session_context.dashboard_uid, ttl_hours=-1)
    response, token = DashboardHubService.create_share_link(**payload)
    assert response.status_code == 201
    session_context.register_share_token(token)

    get_response = DashboardHubService.get_share_link(token)
    assert get_response.status_code == 410
