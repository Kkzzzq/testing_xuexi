from __future__ import annotations

import pytest

from tests.resource_manager import ResourceManager


@pytest.fixture(scope="session")
def session_resources():
    context = ResourceManager.prepare_environment()
    yield context
    ResourceManager.cleanup_environment()


@pytest.fixture(scope="session")
def session_context(session_resources):
    return session_resources


@pytest.fixture(scope="session")
def test_context(session_resources):
    return session_resources


@pytest.fixture()
def dashboard_uid(session_resources):
    assert session_resources.dashboards.dashboard_uid, "dashboard_uid was not created"
    return session_resources.dashboards.dashboard_uid


@pytest.fixture()
def existing_user_login(session_resources):
    assert session_resources.users.existing_user_login, "existing_user_login missing"
    return session_resources.users.existing_user_login
