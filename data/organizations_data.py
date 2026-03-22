from __future__ import annotations

import random


def make_test_organization_body(prefix: str = "testOrganization") -> dict[str, str]:
    rand = random.randint(1000, 9999)
    return {
        "name": f"{prefix}{rand}",
    }


test_organizations_body = make_test_organization_body()

add_in_organizations_body = {
    "loginOrEmail": "Organization",
    "role": "Editor",
}
