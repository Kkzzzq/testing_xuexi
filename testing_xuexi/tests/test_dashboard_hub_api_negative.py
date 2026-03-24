import pytest

from services.dashboard_hub_service import DashboardHubService


@pytest.mark.NegativeDashboardHub
def test_create_subscription_with_unknown_dashboard():
    response = DashboardHubService.create_subscription(
        {
            "dashboard_uid": "not-exists-uid",
            "user_login": "nobody",
            "channel": "email",
            "cron": "0 */6 * * *",
        }
    )
    assert response.status_code == 404


@pytest.mark.NegativeDashboardHub
def test_create_duplicate_subscription(session_context):
    payload = {
        "dashboard_uid": session_context.dashboard_uid,
        "user_login": session_context.existing_user_login,
        "channel": "email",
        "cron": "0 */6 * * *",
    }
    first = DashboardHubService.create_subscription(payload)
    assert first.status_code in (201, 409)
    second = DashboardHubService.create_subscription(payload)
    assert second.status_code == 409


@pytest.mark.NegativeDashboardHub
def test_get_unknown_share_token():
    response = DashboardHubService.get_share_link("missing-token")
    assert response.status_code == 404
