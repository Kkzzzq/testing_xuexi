from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class SubscriptionResponse(BaseModel):
    id: int
    dashboard_uid: str
    user_login: str
    channel: str
    cron: str
    created_at: datetime


class ShareLinkResponse(BaseModel):
    id: int
    dashboard_uid: str
    token: str
    expire_at: datetime | None = None
    view_count: int
    created_at: datetime
