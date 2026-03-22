from __future__ import annotations

import random


def make_random_credentials(prefix: str = "Sergey") -> dict[str, str]:
    rand = random.randint(1000, 9999)
    return {
        "name": f"{prefix}{rand}",
        "email": f"{prefix}{rand}@test.ru",
        "login": f"{prefix}{rand}",
        "password": "password123",
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
    "password": "testPassword",
}
