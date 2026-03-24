from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class DashboardsContext:
    folder_uid: str | None = None
    dashboard_uid: str | None = None


@dataclass
class OrganizationsContext:
    org_id: int | None = None
    org_name: str | None = None


@dataclass
class UsersContext:
    existing_user_id: int | None = None
    existing_user_login: str | None = None
    existing_user_email: str | None = None
    low_access_user_id: int | None = None
    low_access_user_login: str | None = None
    organizations_user_id: int | None = None


@dataclass
class DashboardHubContext:
    subscription_id: int | None = None
    share_token: str | None = None


@dataclass
class TestContext:
    dashboards: DashboardsContext = field(default_factory=DashboardsContext)
    organizations: OrganizationsContext = field(default_factory=OrganizationsContext)
    users: UsersContext = field(default_factory=UsersContext)
    dashboard_hub: DashboardHubContext = field(default_factory=DashboardHubContext)

    @property
    def org_id(self) -> int | None:
        return self.organizations.org_id

    @org_id.setter
    def org_id(self, value: int | None) -> None:
        self.organizations.org_id = value

    @property
    def folder_uid(self) -> str | None:
        return self.dashboards.folder_uid

    @folder_uid.setter
    def folder_uid(self, value: str | None) -> None:
        self.dashboards.folder_uid = value

    @property
    def dashboard_uid(self) -> str | None:
        return self.dashboards.dashboard_uid

    @dashboard_uid.setter
    def dashboard_uid(self, value: str | None) -> None:
        self.dashboards.dashboard_uid = value

    @property
    def existing_user_id(self) -> int | None:
        return self.users.existing_user_id

    @existing_user_id.setter
    def existing_user_id(self, value: int | None) -> None:
        self.users.existing_user_id = value

    @property
    def existing_user_login(self) -> str | None:
        return self.users.existing_user_login

    @existing_user_login.setter
    def existing_user_login(self, value: str | None) -> None:
        self.users.existing_user_login = value

    @property
    def existing_user_email(self) -> str | None:
        return self.users.existing_user_email

    @existing_user_email.setter
    def existing_user_email(self, value: str | None) -> None:
        self.users.existing_user_email = value

    @property
    def low_access_user_id(self) -> int | None:
        return self.users.low_access_user_id

    @low_access_user_id.setter
    def low_access_user_id(self, value: int | None) -> None:
        self.users.low_access_user_id = value

    @property
    def low_access_user_login(self) -> str | None:
        return self.users.low_access_user_login

    @low_access_user_login.setter
    def low_access_user_login(self, value: str | None) -> None:
        self.users.low_access_user_login = value

    @property
    def subscription_id(self) -> int | None:
        return self.dashboard_hub.subscription_id

    @subscription_id.setter
    def subscription_id(self, value: int | None) -> None:
        self.dashboard_hub.subscription_id = value

    @property
    def share_token(self) -> str | None:
        return self.dashboard_hub.share_token

    @share_token.setter
    def share_token(self, value: str | None) -> None:
        self.dashboard_hub.share_token = value

    def to_dict(self) -> dict:
        return asdict(self)
