from __future__ import annotations

import random
import time


def make_organization_body(prefix: str = "testOrganization") -> dict[str, str]:
    suffix = f"{int(time.time() * 1000)}{random.randint(100, 999)}"
    return {"name": f"{prefix}{suffix}"}


make_test_organization_body = make_organization_body

test_organizations_body = make_organization_body()
add_in_organizations_body = {
    "loginOrEmail": "Organization",
    "role": "Editor",
}
