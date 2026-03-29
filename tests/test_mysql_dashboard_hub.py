import allure
import pytest

from data.dashboard_hub_data import make_share_link_payload, make_subscription_payload
from services.dashboard_hub_service import DashboardHubService
from services.mysql_service import MySQLService


@allure.label("fault_scenario", "subscription_mysql_persistence")
@pytest.mark.sql
def test_subscription_written_to_mysql(session_context):
    payload = make_subscription_payload(
        session_context.dashboard_uid,
        session_context.low_access_user_login,
        channel="slack",
    )
    response, subscription_id = DashboardHubService.create_subscription(**payload)
    assert response.status_code == 201

    session_context.register_subscription(subscription_id)

    row = MySQLService.fetch_subscription_by_id(subscription_id)
    assert row is not None
    assert row["dashboard_uid"] == session_context.dashboard_uid
    assert row["user_login"] == session_context.low_access_user_login
    assert row["channel"] == "slack"

    delete_response = DashboardHubService.delete_subscription(subscription_id)
    assert delete_response.status_code == 200

    session_context.forget_subscription(subscription_id)

    deleted_row = MySQLService.fetch_subscription_by_id(subscription_id)
    assert deleted_row is None


@allure.label("fault_scenario", "share_link_mysql_write_and_view_count")
@pytest.mark.sql
def test_share_link_written_to_mysql_and_view_count_updated(session_context):
    payload = make_share_link_payload(session_context.dashboard_uid)
    response, token = DashboardHubService.create_share_link(**payload)
    assert response.status_code == 201

    session_context.register_share_token(token)

    row = MySQLService.fetch_share_link_by_token(token)
    assert row is not None
    assert row["dashboard_uid"] == session_context.dashboard_uid
    assert row["view_count"] == 0

    get_response = DashboardHubService.get_share_link(token)
    assert get_response.status_code == 200

    updated_row = MySQLService.fetch_share_link_by_token(token)
    assert updated_row is not None
    assert updated_row["view_count"] >= 1

    delete_response = DashboardHubService.delete_share_link(token)
    assert delete_response.status_code == 200

    session_context.forget_share_token(token)
