from __future__ import annotations

import copy
import random
import time


def make_random_credentials(prefix: str = "User") -> dict[str, str]:
    suffix = f"{int(time.time() * 1000)}{random.randint(100, 999)}"
    login = f"{prefix}{suffix}"
    return {
        "name": login,
        "email": f"{login.lower()}@test.local",
        "login": login,
        "password": "test123",
    }


existing_credentials = {
    "name": "SergeySergey",
    "email": "SergeySergey@test.ru",
    "login": "SergeySergey",
    "password": "test123",
}

low_access_credentials = {
    "name": "LowAccess",
    "email": "LowAccess@test.ru",
    "login": "LowAccess",
    "password": "test",
}

organizations_user = {
    "name": "Organization",
    "email": "Organization@test.ru",
    "login": "Organization",
    "password": "test",
}

change_password = {
    "password": "testPassword123!",
}


def make_user_credentials(kind: str = "existing_user") -> dict[str, str]:
    mapping = {
        "existing_user": existing_credentials,
        "low_access_user": low_access_credentials,
        "organizations_user": organizations_user,
    }
    if kind in mapping:
        return copy.deepcopy(mapping[kind])
    return make_random_credentials(kind)
