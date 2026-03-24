from __future__ import annotations

from pydantic import BaseModel


class CreateFolderResponse(BaseModel):
    id: int | None = None
    uid: str
    title: str


class CreateDashboardStatus(BaseModel):
    id: int | None = None
    slug: str | None = None
    status: str = "success"
    uid: str
    version: int | None = None


class DashboardPayload(BaseModel):
    id: int
    uid: str
    title: str
    timezone: str | None = None


class GetDashboardSchema(BaseModel):
    dashboard: DashboardPayload
    meta: dict


class GetDashboardsWithIncorrectCredentialsSchema(BaseModel):
    message: str = "invalid username or password"
    messageId: str | None = None
