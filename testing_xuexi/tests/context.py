from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class TestContext:
    org_id: int | None = None
    folder_uid: str | None = None
    dashboard_uid: str | None = None
    existing_user_id: int | None = None
    existing_user_login: str | None = None
    existing_user_email: str | None = None
    low_access_user_id: int | None = None
    low_access_user_login: str | None = None
    subscription_id: int | None = None
    share_token: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)
