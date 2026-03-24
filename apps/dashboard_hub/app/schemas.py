from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SubscriptionCreate(BaseModel):
    dashboard_uid: str = Field(min_length=3)
    user_login: str = Field(min_length=1)
    channel: str = Field(default="email")
    cron: str = Field(default="0 */6 * * *")


class SubscriptionOut(BaseModel):
    id: int
    dashboard_uid: str
    user_login: str
    channel: str
    cron: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SubscriptionsListOut(BaseModel):
    dashboard_uid: str
    items: list[SubscriptionOut]


class ShareLinkCreate(BaseModel):
    dashboard_uid: str = Field(min_length=3)
    expire_at: datetime | None = None


class ShareLinkOut(BaseModel):
    id: int
    dashboard_uid: str
    token: str
    expire_at: datetime | None = None
    view_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class DashboardSummaryOut(BaseModel):
    dashboard_uid: str
    title: str
    url: str | None = None
