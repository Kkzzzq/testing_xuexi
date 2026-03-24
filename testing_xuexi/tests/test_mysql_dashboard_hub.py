import pytest

from data.dashboard_hub_data import make_share_link_payload, make_subscription_payload
from services.dashboard_hub_service import DashboardHubService
from services.mysql_service import MySQLService


@pytest.mark.sql
def test_subscription_written_to_mysql(session_context):
    response = DashboardHubService.create_subscription(
        make_subscription_payload(session_context.dashboard_uid, session_context.existing_user_login, channel="slack")
    )
    assert response.status_code in (201, 409)
    payload = response.json()
    row = MySQLService.fetch_subscription_by_id(payload["id"])
    assert row is not None
    assert row["dashboard_uid"] == session_context.dashboard_uid


@pytest.mark.sql
def test_share_link_written_to_mysql(session_context):
    response = DashboardHubService.create_share_link(make_share_link_payload(session_context.dashboard_uid))
    assert response.status_code == 201
    payload = response.json()
    row = MySQLService.fetch_share_link_by_token(payload["token"])
    assert row is not None
    assert row["dashboard_uid"] == session_context.dashboard_uid
