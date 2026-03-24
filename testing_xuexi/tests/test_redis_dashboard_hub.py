import pytest

from data.dashboard_hub_data import make_share_link_payload, make_subscription_payload
from services.dashboard_hub_service import DashboardHubService
from services.redis_service import RedisService


@pytest.mark.cache
def test_subscriptions_are_cached(session_context):
    DashboardHubService.create_subscription(
        make_subscription_payload(session_context.dashboard_uid, session_context.existing_user_login, channel="webhook")
    )
    response = DashboardHubService.get_subscriptions(session_context.dashboard_uid)
    assert response.status_code == 200

    key = f"dashhub:subscriptions:{session_context.dashboard_uid}"
    cached_payload = RedisService.get_json(key)
    assert cached_payload is not None
    assert cached_payload["dashboard_uid"] == session_context.dashboard_uid


@pytest.mark.cache
def test_share_link_is_cached(session_context):
    create_response = DashboardHubService.create_share_link(make_share_link_payload(session_context.dashboard_uid))
    assert create_response.status_code == 201
    token = create_response.json()["token"]

    response = DashboardHubService.get_share_link(token)
    assert response.status_code == 200

    key = f"dashhub:share:{token}"
    cached_payload = RedisService.get_json(key)
    assert cached_payload is not None
    assert cached_payload["token"] == token
