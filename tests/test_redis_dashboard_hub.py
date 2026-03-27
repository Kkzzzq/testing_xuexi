import json

import allure
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

    session_context.register_subscription(subscription_id)

    list_response = DashboardHubService.list_subscriptions(session_context.dashboard_uid)
    assert list_response.status_code == 200

    key = f"dashhub:subscriptions:{session_context.dashboard_uid}"
    cached_payload = RedisService.get_json(key)
    assert cached_payload is not None
    assert cached_payload["dashboard_uid"] == session_context.dashboard_uid

    delete_response = DashboardHubService.delete_subscription(subscription_id)
    assert delete_response.status_code == 200

    session_context.forget_subscription(subscription_id)
    assert RedisService.exists(key) is False


@pytest.mark.cache
def test_share_link_is_cached_and_invalidated(session_context):
    create_response, token = DashboardHubService.create_share_link(
        **make_share_link_payload(session_context.dashboard_uid)
    )
    assert create_response.status_code == 201

    session_context.register_share_token(token)

    response = DashboardHubService.get_share_link(token)
    assert response.status_code == 200

    key = f"dashhub:share:{token}"
    cached_payload = RedisService.get_json(key)
    assert cached_payload is not None
    assert cached_payload["token"] == token

    delete_response = DashboardHubService.delete_share_link(token)
    assert delete_response.status_code == 200

    session_context.forget_share_token(token)
    assert RedisService.exists(key) is False


@pytest.mark.cache
def test_dashboard_summary_is_cached(session_context):
    response = DashboardHubService.get_dashboard_summary(session_context.dashboard_uid)
    assert response.status_code == 200

    payload = response.json()
    key = (
        f"dashhub:summary:{session_context.dashboard_uid}:"
        f"{payload['provider']}:{payload['model']}:{payload['prompt_version']}"
    )
    cached_payload = RedisService.get_json(key)

    print("\n========== Cached Dashboard AI Summary ==========")
    print(f"redis_key: {key}")
    print(f"source: {payload['source']}")
    print(f"ai_summary: {payload['ai_summary']}")
    print("================================================\n")

    allure.attach(
        key,
        name="Summary Redis Key",
        attachment_type=allure.attachment_type.TEXT,
    )
    allure.attach(
        json.dumps(cached_payload, ensure_ascii=False, indent=2),
        name="Cached Dashboard Summary Payload",
        attachment_type=allure.attachment_type.JSON,
    )
    allure.attach(
        cached_payload["ai_summary"],
        name="Cached AI Summary Content",
        attachment_type=allure.attachment_type.TEXT,
    )

    assert cached_payload is not None
    assert cached_payload["dashboard_uid"] == session_context.dashboard_uid
    assert cached_payload["ai_summary"] == payload["ai_summary"]
    assert cached_payload["source"] == payload["source"]
