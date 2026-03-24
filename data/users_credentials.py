from __future__ import annotations

import time


def make_user_credentials(prefix: str = "user") -> dict:
    suffix = int(time.time() * 1000)
    login = f"{prefix}_{suffix}"
    return {
        "name": f"{prefix.capitalize()} {suffix}",
        "email": f"{login}@example.com",
        "login": login,
        "password": "Test123456!",
    }


change_password = {
    "oldPassword": "Test123456!",
    "newPassword": "Test123456!x",
    "confirmNew": "Test123456!x",
}
