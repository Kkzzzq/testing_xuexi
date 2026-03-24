from __future__ import annotations

import time


def make_organization_body(name: str | None = None) -> dict:
    return {"name": name or f"org-auto-{int(time.time() * 1000)}"}


def make_add_user_body(login_or_email: str, role: str = "Viewer") -> dict:
    return {"loginOrEmail": login_or_email, "role": role}
