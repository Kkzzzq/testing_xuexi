from __future__ import annotations

import os

from locust import HttpUser, between, task


DASHBOARD_UID = os.getenv("LOCUST_DASHBOARD_UID", "replace-me")
SHARE_TOKEN = os.getenv("LOCUST_SHARE_TOKEN", "replace-me")


class DashboardHubUser(HttpUser):
    wait_time = between(1, 3)

    @task(4)
    def list_subscriptions(self):
        if DASHBOARD_UID != "replace-me":
            self.client.get(f"/api/v1/dashboards/{DASHBOARD_UID}/subscriptions", name="/dashboards/:uid/subscriptions")

    @task(4)
    def get_share_link(self):
        if SHARE_TOKEN != "replace-me":
            self.client.get(f"/api/v1/share-links/{SHARE_TOKEN}", name="/share-links/:token")

    @task(1)
    def create_subscription(self):
        if DASHBOARD_UID != "replace-me":
            self.client.post(
                "/api/v1/subscriptions",
                json={
                    "dashboard_uid": DASHBOARD_UID,
                    "user_login": "locust_user",
                    "channel": "email",
                    "cron": "0 */6 * * *",
                },
                name="/subscriptions",
            )
