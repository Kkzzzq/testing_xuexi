from __future__ import annotations

from services.api_users_service import ApiUsersService
from services.db_service import DBService


def remove_user_if_exists(login: str) -> None:
    user = DBService.find_user_by_login(login)
    if user:
        ApiUsersService.delete_api_user(user_id=user[3])
