from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class UserContext:
    existing_user_id: int | None = None
    low_access_user_id: int | None = None
    organizations_user_id: int | None = None


@dataclass
class DashboardContext:
    folder_uid: str | None = None
    dashboard_uid: str | None = None
    title: str = "Dashboard for API"


@dataclass
class OrganizationContext:
    org_id: int | None = None
    org_name: str | None = None


@dataclass
class TestContext:
    users: UserContext = field(default_factory=UserContext)
    dashboards: DashboardContext = field(default_factory=DashboardContext)
    organizations: OrganizationContext = field(default_factory=OrganizationContext)
