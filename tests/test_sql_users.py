from __future__ import annotations

import allure
import pytest

from data.users_credentials import make_random_credentials
from helpers.schemas.user_schema import CreateUserSchema
from services.api_users_service import ApiUsersService
from services.db_service import DBService
from services.utils import assert_json_response, validate_status_code_and_body


@allure.title("User created by API should be visible in Grafana SQLite")
@allure.description("Read-only SQL validation against Grafana internal SQLite database")
@allure.tag("DB_users", "Positive")
@allure.id("sql_user_visibility")
@pytest.mark.sql
def test_user_created_via_api_is_visible_in_sqlite():
    payload = make_random_credentials("SqlUser")
    user_id = None

    try:
        response, user_id = ApiUsersService.create_api_user(payload)
        validate_status_code_and_body(response, CreateUserSchema, 200)
        assert_json_response(response)

        user = DBService.find_user_by_email(payload["email"])
        assert user is not None
        assert user[0] == payload["login"]
        assert user[1] == payload["email"]
        assert user[2] == payload["name"]
        assert user[3] == user_id
    finally:
        if user_id is not None:
            ApiUsersService.delete_api_user(userid=user_id)
