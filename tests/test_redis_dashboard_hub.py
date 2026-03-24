import pytest

from data.dashboard_hub_data import make_share_link_payload, make_subscription_payload
from services.dashboard_hub_service import DashboardHubService
from services.redis_service import RedisService


@pytest.mark.cache
def test_subscriptions_are_cached_and_invalidated(session_context):
    payload = make_subscription_payload(
        session_context.dashboard_uid,
        session_context.low_access_user_login,
        channel="webhook",
    )
    create_response, subscription_id = DashboardHubService.create_subscription(**payload)
    assert create_response.status_code == 201
    session_context.subscription_id = subscription_id

    list_response = DashboardHubService.list_subscriptions(session_context.dashboard_uid)
    assert list_response.status_code == 200

    key = f"dashhub:subscriptions:{session_context.dashboard_uid}"
    cached_payload = RedisService.get_json(key)
    assert cached_payload is not None
    assert cached_payload["dashboard_uid"] == session_context.dashboard_uid

    delete_response = DashboardHubService.delete_subscription(subscription_id)
    assert delete_response.status_code == 200
    session_context.subscription_id = None

    assert RedisService.exists(key) is False


@pytest.mark.cache
def test_share_link_is_cached_and_invalidated(session_context):
    create_response, token = DashboardHubService.create_share_link(
        **make_share_link_payload(session_context.dashboard_uid)
    )
    assert create_response.status_code == 201
    session_context.share_token = token

    response = DashboardHubService.get_share_link(token)
    assert response.status_code == 200

    key = f"dashhub:share:{token}"
    cached_payload = RedisService.get_json(key)
    assert cached_payload is not None
    assert cached_payload["token"] == token

    delete_response = DashboardHubService.delete_share_link(token)
    assert delete_response.status_code == 200
    session_context.share_token = None

    assert RedisService.exists(key) is False
