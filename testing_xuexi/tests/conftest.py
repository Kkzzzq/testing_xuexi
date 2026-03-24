from __future__ import annotations

import pytest

from services.dashboard_hub_service import DashboardHubService
from tests.resource_manager import ResourceManager


@pytest.fixture(scope="session")
def session_context():
    context = ResourceManager.prepare_environment()
    yield context
    try:
        if context.subscription_id:
            DashboardHubService.delete_subscription(context.subscription_id)
    finally:
        ResourceManager.cleanup_environment()


@pytest.fixture()
def dashboard_uid(session_context):
    assert session_context.dashboard_uid, "dashboard_uid was not created"
    return session_context.dashboard_uid


@pytest.fixture()
def existing_user_login(session_context):
    assert session_context.existing_user_login, "existing_user_login missing"
    return session_context.existing_user_login
