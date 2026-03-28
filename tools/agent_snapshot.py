from __future__ import annotations

from typing import Any

from tools.agent_evidence import (
    collect_metrics_snapshot,
    collect_share_link_snapshot,
    collect_subscription_snapshot,
    collect_summary_snapshot,
    diff_metrics,
)

SUBSCRIPTION_SCENARIOS = {
    "subscription_persistence",
    "subscription_conflict",
    "subscription_cache_invalidation",
    "subscription_unknown_dashboard",
    "illegal_subscription_channel",
}

SHARE_SCENARIOS = {
    "share_link_view_count",
    "share_link_cache_invalidation",
    "expired_share_link",
    "unknown_share_token",
}


def capture_snapshot(scenario: str, runtime: dict[str, Any]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {"metrics": collect_metrics_snapshot()}

    if scenario in SUBSCRIPTION_SCENARIOS and all(
        runtime.get(key) is not None for key in ("dashboard_uid", "user_login", "channel")
    ):
        snapshot["subscription"] = collect_subscription_snapshot(
            dashboard_uid=runtime["dashboard_uid"],
            user_login=runtime["user_login"],
            channel=runtime["channel"],
            subscription_id=runtime.get("subscription_id"),
        )

    if scenario in SHARE_SCENARIOS and runtime.get("token"):
        snapshot["share_link"] = collect_share_link_snapshot(runtime["token"])

    if scenario == "summary_cache" and runtime.get("dashboard_uid"):
        snapshot["summary"] = collect_summary_snapshot(
            dashboard_uid=runtime["dashboard_uid"],
            summary_key=runtime.get("summary_key"),
        )

    return snapshot


def diff_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    diff: dict[str, Any] = {}
    for key in sorted(set(before) | set(after)):
        before_value = before.get(key)
        after_value = after.get(key)
        if key == "metrics":
            before_metrics = (before_value or {}).get("parsed", {})
            after_metrics = (after_value or {}).get("parsed", {})
            metric_diff = diff_metrics(before_metrics, after_metrics)
            if metric_diff:
                diff[key] = metric_diff
            continue
        if before_value != after_value:
            diff[key] = {"before": before_value, "after": after_value}
    return diff
