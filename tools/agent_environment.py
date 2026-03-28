from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from services.api_dashboards_service import ApiDashboardsService
from services.dashboard_hub_service import DashboardHubService


@dataclass(slots=True)
class AgentEnvironmentContext:
    folder_uid: str | None = None
    dashboard_uid: str | None = None
    existing_user_login: str = ""
    low_access_user_login: str = ""
    subscription_ids: list[int] = field(default_factory=list)
    share_tokens: list[str] = field(default_factory=list)

    def register_subscription(self, subscription_id: int | None) -> None:
        if isinstance(subscription_id, int) and subscription_id not in self.subscription_ids:
            self.subscription_ids.append(subscription_id)

    def register_share_token(self, token: str | None) -> None:
        if token and token not in self.share_tokens:
            self.share_tokens.append(token)

    def forget_subscription(self, subscription_id: int | None) -> None:
        if subscription_id is None:
            return
        self.subscription_ids = [item for item in self.subscription_ids if item != subscription_id]

    def forget_share_token(self, token: str | None) -> None:
        if not token:
            return
        self.share_tokens = [item for item in self.share_tokens if item != token]


class AgentEnvironmentManager:
    @staticmethod
    def prepare_environment() -> AgentEnvironmentContext:
        suffix = f"{int(time.time() * 1000)}"
        context = AgentEnvironmentContext(
            existing_user_login=f"agent_existing_{suffix}",
            low_access_user_login=f"agent_low_{suffix}",
        )

        folder_response, folder_uid = ApiDashboardsService.create_folder(
            body={"title": f"fault-agent-folder-{suffix}"}
        )
        if not folder_response.ok or not folder_uid:
            raise RuntimeError(f"failed to create fault-agent folder: {folder_response.text}")
        context.folder_uid = folder_uid

        dashboard_response, dashboard_uid = ApiDashboardsService.create_dashboard(folder_uid)
        if not dashboard_response.ok or not dashboard_uid:
            try:
                ApiDashboardsService.delete_folder(folder_uid)
            except Exception:
                pass
            raise RuntimeError(f"failed to create fault-agent dashboard: {dashboard_response.text}")
        context.dashboard_uid = dashboard_uid
        return context

    @staticmethod
    def cleanup_environment(context: AgentEnvironmentContext) -> None:
        for token in reversed(context.share_tokens):
            try:
                DashboardHubService.delete_share_link(token)
            except Exception as exc:  # noqa: BLE001
                logging.warning("Failed to cleanup share token %s: %s", token, exc)

        for subscription_id in reversed(context.subscription_ids):
            try:
                DashboardHubService.delete_subscription(subscription_id)
            except Exception as exc:  # noqa: BLE001
                logging.warning("Failed to cleanup subscription %s: %s", subscription_id, exc)

        if context.dashboard_uid:
            try:
                ApiDashboardsService.delete_dashboard_by_uid(context.dashboard_uid)
            except Exception as exc:  # noqa: BLE001
                logging.warning("Failed to cleanup dashboard %s: %s", context.dashboard_uid, exc)

        if context.folder_uid:
            try:
                ApiDashboardsService.delete_folder(context.folder_uid)
            except Exception as exc:  # noqa: BLE001
                logging.warning("Failed to cleanup folder %s: %s", context.folder_uid, exc)
