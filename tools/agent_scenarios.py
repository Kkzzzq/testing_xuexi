from __future__ import annotations

import json
from typing import Any

from data.dashboard_hub_data import make_share_link_payload, make_subscription_payload
from services.dashboard_hub_service import DashboardHubService
from services.redis_service import RedisService
from tools.agent_environment import AgentEnvironmentContext
from tools.agent_evidence import build_summary_cache_key
from tools.agent_snapshot import capture_snapshot, diff_snapshots


def _body_excerpt(response) -> str:
    try:
        payload = response.json()
        text = json.dumps(payload, ensure_ascii=False)
    except Exception:
        text = response.text
    return text[:300]


def _step(step_name: str, response, expected_status: int | tuple[int, ...]) -> dict[str, Any]:
    return {
        "step": step_name,
        "status_code": response.status_code,
        "expected_status": expected_status,
        "body_excerpt": _body_excerpt(response),
    }


def _finalize_result(
    *,
    scenario: str,
    runtime: dict[str, Any],
    before: dict[str, Any],
    after: dict[str, Any],
    http_steps: list[dict[str, Any]],
    intermediate: dict[str, Any],
    anomalies: list[str],
    execution_error: str | None = None,
) -> dict[str, Any]:
    return {
        "scenario": scenario,
        "runtime": runtime,
        "http_steps": http_steps,
        "intermediate": intermediate,
        "anomalies": anomalies,
        "failure_reproduced": bool(anomalies),
        "execution_error": execution_error,
        "snapshot": {
            "before": before,
            "after": after,
            "diff": diff_snapshots(before, after),
        },
    }


def _run_subscription_persistence(context: AgentEnvironmentContext) -> dict[str, Any]:
    scenario = "subscription_persistence"
    runtime = {
        "dashboard_uid": context.dashboard_uid,
        "user_login": context.low_access_user_login,
        "channel": "slack",
    }
    before = capture_snapshot(scenario, runtime)
    http_steps: list[dict[str, Any]] = []
    intermediate: dict[str, Any] = {}
    anomalies: list[str] = []

    response, subscription_id = DashboardHubService.create_subscription(
        **make_subscription_payload(context.dashboard_uid, context.low_access_user_login, channel="slack")
    )
    runtime["subscription_id"] = subscription_id
    if subscription_id:
        context.register_subscription(subscription_id)
    http_steps.append(_step("create_subscription", response, 201))
    after = capture_snapshot(scenario, runtime)

    if response.status_code != 201:
        anomalies.append("unexpected_http_create_status")

    subscription_state = after.get("subscription", {})
    if subscription_state.get("business_key_count", 0) < 1:
        anomalies.append("mysql_subscription_missing")
    if subscription_state.get("subscription_row") is None:
        anomalies.append("mysql_subscription_row_missing")

    return _finalize_result(
        scenario=scenario,
        runtime=runtime,
        before=before,
        after=after,
        http_steps=http_steps,
        intermediate=intermediate,
        anomalies=anomalies,
    )


def _run_subscription_conflict(context: AgentEnvironmentContext) -> dict[str, Any]:
    scenario = "subscription_conflict"
    runtime = {
        "dashboard_uid": context.dashboard_uid,
        "user_login": context.existing_user_login,
        "channel": "webhook",
    }
    before = capture_snapshot(scenario, runtime)
    http_steps: list[dict[str, Any]] = []
    intermediate: dict[str, Any] = {}
    anomalies: list[str] = []

    payload = make_subscription_payload(context.dashboard_uid, context.existing_user_login, channel="webhook")
    first_response, first_id = DashboardHubService.create_subscription(**payload)
    runtime["subscription_id"] = first_id
    if first_id:
        context.register_subscription(first_id)
    http_steps.append(_step("create_subscription_first", first_response, 201))

    second_response, _ = DashboardHubService.create_subscription(**payload)
    http_steps.append(_step("create_subscription_second", second_response, 409))
    after = capture_snapshot(scenario, runtime)

    if first_response.status_code != 201:
        anomalies.append("unexpected_http_first_create_status")
    if second_response.status_code != 409:
        anomalies.append("unexpected_http_second_create_status")

    subscription_state = after.get("subscription", {})
    if subscription_state.get("business_key_count") != 1:
        anomalies.append("mysql_duplicate_subscription_rows")

    return _finalize_result(
        scenario=scenario,
        runtime=runtime,
        before=before,
        after=after,
        http_steps=http_steps,
        intermediate=intermediate,
        anomalies=anomalies,
    )


def _run_subscription_cache_invalidation(context: AgentEnvironmentContext) -> dict[str, Any]:
    scenario = "subscription_cache_invalidation"
    runtime = {
        "dashboard_uid": context.dashboard_uid,
        "user_login": context.low_access_user_login,
        "channel": "webhook",
    }
    before = capture_snapshot(scenario, runtime)
    http_steps: list[dict[str, Any]] = []
    intermediate: dict[str, Any] = {}
    anomalies: list[str] = []

    payload = make_subscription_payload(context.dashboard_uid, context.low_access_user_login, channel="webhook")
    create_response, subscription_id = DashboardHubService.create_subscription(**payload)
    runtime["subscription_id"] = subscription_id
    if subscription_id:
        context.register_subscription(subscription_id)
    http_steps.append(_step("create_subscription", create_response, 201))

    list_response = DashboardHubService.list_subscriptions(context.dashboard_uid)
    http_steps.append(_step("list_subscriptions", list_response, 200))
    subscription_cache_key = f"dashhub:subscriptions:{context.dashboard_uid}"
    intermediate["cache_after_list"] = RedisService.get_json(subscription_cache_key)

    delete_response = DashboardHubService.delete_subscription(subscription_id)
    http_steps.append(_step("delete_subscription", delete_response, 200))
    context.forget_subscription(subscription_id)
    after = capture_snapshot(scenario, runtime)

    if create_response.status_code != 201:
        anomalies.append("unexpected_http_create_status")
    if list_response.status_code != 200:
        anomalies.append("unexpected_http_list_status")
    if delete_response.status_code != 200:
        anomalies.append("unexpected_http_delete_status")
    if intermediate["cache_after_list"] is None:
        anomalies.append("redis_subscription_cache_missing_after_list")
    if after.get("subscription", {}).get("cache_exists"):
        anomalies.append("redis_subscription_cache_still_exists_after_delete")
    if after.get("subscription", {}).get("business_key_count") not in (0, None):
        anomalies.append("mysql_subscription_row_still_exists_after_delete")

    return _finalize_result(
        scenario=scenario,
        runtime=runtime,
        before=before,
        after=after,
        http_steps=http_steps,
        intermediate=intermediate,
        anomalies=anomalies,
    )


def _run_share_link_view_count(context: AgentEnvironmentContext) -> dict[str, Any]:
    scenario = "share_link_view_count"
    runtime = {"dashboard_uid": context.dashboard_uid}
    before = capture_snapshot(scenario, runtime)
    http_steps: list[dict[str, Any]] = []
    intermediate: dict[str, Any] = {}
    anomalies: list[str] = []

    create_response, token = DashboardHubService.create_share_link(**make_share_link_payload(context.dashboard_uid))
    runtime["token"] = token
    context.register_share_token(token)
    http_steps.append(_step("create_share_link", create_response, 201))

    get_response = DashboardHubService.get_share_link(token)
    http_steps.append(_step("get_share_link", get_response, 200))
    after = capture_snapshot(scenario, runtime)

    if create_response.status_code != 201:
        anomalies.append("unexpected_http_create_status")
    if get_response.status_code != 200:
        anomalies.append("unexpected_http_get_status")

    share_state = after.get("share_link", {})
    mysql_row = share_state.get("mysql_row") or {}
    if not mysql_row:
        anomalies.append("mysql_share_link_missing")
    elif int(mysql_row.get("view_count", 0)) < 1:
        anomalies.append("mysql_view_count_not_incremented")

    return _finalize_result(
        scenario=scenario,
        runtime=runtime,
        before=before,
        after=after,
        http_steps=http_steps,
        intermediate=intermediate,
        anomalies=anomalies,
    )


def _run_share_link_cache_invalidation(context: AgentEnvironmentContext) -> dict[str, Any]:
    scenario = "share_link_cache_invalidation"
    runtime = {"dashboard_uid": context.dashboard_uid}
    before = capture_snapshot(scenario, runtime)
    http_steps: list[dict[str, Any]] = []
    intermediate: dict[str, Any] = {}
    anomalies: list[str] = []

    create_response, token = DashboardHubService.create_share_link(**make_share_link_payload(context.dashboard_uid))
    runtime["token"] = token
    context.register_share_token(token)
    http_steps.append(_step("create_share_link", create_response, 201))

    get_response = DashboardHubService.get_share_link(token)
    http_steps.append(_step("get_share_link", get_response, 200))
    share_cache_key = f"dashhub:share:{token}"
    intermediate["cache_after_get"] = RedisService.get_json(share_cache_key)

    delete_response = DashboardHubService.delete_share_link(token)
    http_steps.append(_step("delete_share_link", delete_response, 200))
    context.forget_share_token(token)
    after = capture_snapshot(scenario, runtime)

    if create_response.status_code != 201:
        anomalies.append("unexpected_http_create_status")
    if get_response.status_code != 200:
        anomalies.append("unexpected_http_get_status")
    if delete_response.status_code != 200:
        anomalies.append("unexpected_http_delete_status")
    if intermediate["cache_after_get"] is None:
        anomalies.append("redis_share_cache_missing_after_get")
    if after.get("share_link", {}).get("cache_exists"):
        anomalies.append("redis_share_cache_still_exists_after_delete")
    if after.get("share_link", {}).get("mysql_row") is not None:
        anomalies.append("mysql_share_link_row_still_exists_after_delete")

    return _finalize_result(
        scenario=scenario,
        runtime=runtime,
        before=before,
        after=after,
        http_steps=http_steps,
        intermediate=intermediate,
        anomalies=anomalies,
    )


def _run_summary_cache(context: AgentEnvironmentContext) -> dict[str, Any]:
    scenario = "summary_cache"
    runtime = {
        "dashboard_uid": context.dashboard_uid,
        "summary_key": build_summary_cache_key(context.dashboard_uid),
    }
    before = capture_snapshot(scenario, runtime)
    http_steps: list[dict[str, Any]] = []
    intermediate: dict[str, Any] = {}
    anomalies: list[str] = []

    response = DashboardHubService.get_dashboard_summary(context.dashboard_uid)
    http_steps.append(_step("get_dashboard_summary", response, 200))

    if response.status_code == 200:
        payload = response.json()
        runtime["summary_key"] = (
            f"dashhub:summary:{context.dashboard_uid}:"
            f"{payload['provider']}:{payload['model']}:{payload['prompt_version']}"
        )
        intermediate["summary_response"] = payload
    after = capture_snapshot(scenario, runtime)

    if response.status_code != 200:
        anomalies.append("unexpected_http_summary_status")
    summary_state = after.get("summary", {})
    if not summary_state.get("cache_exists"):
        anomalies.append("redis_summary_cache_missing_after_get")
    if intermediate.get("summary_response") and summary_state.get("cache_payload"):
        cached_payload = summary_state["cache_payload"]
        if cached_payload.get("ai_summary") != intermediate["summary_response"].get("ai_summary"):
            anomalies.append("redis_summary_payload_mismatch")
        source = intermediate["summary_response"].get("source")
        if source not in {"ai", "fallback"}:
            anomalies.append("summary_source_unexpected")

    return _finalize_result(
        scenario=scenario,
        runtime=runtime,
        before=before,
        after=after,
        http_steps=http_steps,
        intermediate=intermediate,
        anomalies=anomalies,
    )


def _run_expired_share_link(context: AgentEnvironmentContext) -> dict[str, Any]:
    scenario = "expired_share_link"
    runtime = {"dashboard_uid": context.dashboard_uid}
    before = capture_snapshot(scenario, runtime)
    http_steps: list[dict[str, Any]] = []
    intermediate: dict[str, Any] = {}
    anomalies: list[str] = []

    create_response, token = DashboardHubService.create_share_link(
        **make_share_link_payload(context.dashboard_uid, ttl_hours=-1)
    )
    runtime["token"] = token
    context.register_share_token(token)
    http_steps.append(_step("create_expired_share_link", create_response, 201))

    get_response = DashboardHubService.get_share_link(token)
    http_steps.append(_step("get_expired_share_link", get_response, 410))
    after = capture_snapshot(scenario, runtime)

    if create_response.status_code != 201:
        anomalies.append("unexpected_http_create_status")
    if get_response.status_code != 410:
        anomalies.append("unexpected_http_get_expired_status")
    if after.get("share_link", {}).get("cache_exists"):
        anomalies.append("redis_expired_share_cache_still_exists")

    return _finalize_result(
        scenario=scenario,
        runtime=runtime,
        before=before,
        after=after,
        http_steps=http_steps,
        intermediate=intermediate,
        anomalies=anomalies,
    )


def _run_subscription_unknown_dashboard(context: AgentEnvironmentContext) -> dict[str, Any]:
    scenario = "subscription_unknown_dashboard"
    runtime = {
        "dashboard_uid": "not-exists-uid",
        "user_login": context.existing_user_login,
        "channel": "email",
    }
    before = capture_snapshot(scenario, runtime)
    http_steps: list[dict[str, Any]] = []
    intermediate: dict[str, Any] = {}
    anomalies: list[str] = []

    response, _ = DashboardHubService.create_subscription(
        dashboard_uid="not-exists-uid",
        user_login=context.existing_user_login,
        channel="email",
        cron="0 */6 * * *",
    )
    http_steps.append(_step("create_subscription_unknown_dashboard", response, 404))
    after = capture_snapshot(scenario, runtime)

    if response.status_code != 404:
        anomalies.append("unexpected_http_unknown_dashboard_status")
    if after.get("subscription", {}).get("business_key_count") not in (0, None):
        anomalies.append("mysql_subscription_created_for_unknown_dashboard")

    return _finalize_result(
        scenario=scenario,
        runtime=runtime,
        before=before,
        after=after,
        http_steps=http_steps,
        intermediate=intermediate,
        anomalies=anomalies,
    )


def _run_unknown_share_token(context: AgentEnvironmentContext) -> dict[str, Any]:
    scenario = "unknown_share_token"
    runtime = {"dashboard_uid": context.dashboard_uid, "token": "missing-token"}
    before = capture_snapshot(scenario, runtime)
    http_steps: list[dict[str, Any]] = []
    intermediate: dict[str, Any] = {}
    anomalies: list[str] = []

    response = DashboardHubService.get_share_link("missing-token")
    http_steps.append(_step("get_unknown_share_token", response, 404))
    after = capture_snapshot(scenario, runtime)

    if response.status_code != 404:
        anomalies.append("unexpected_http_unknown_share_status")
    share_state = after.get("share_link", {})
    if share_state.get("mysql_row") is not None:
        anomalies.append("mysql_unknown_share_token_row_exists")
    if share_state.get("cache_exists"):
        anomalies.append("redis_unknown_share_token_cache_exists")

    return _finalize_result(
        scenario=scenario,
        runtime=runtime,
        before=before,
        after=after,
        http_steps=http_steps,
        intermediate=intermediate,
        anomalies=anomalies,
    )


def _run_illegal_subscription_channel(context: AgentEnvironmentContext) -> dict[str, Any]:
    scenario = "illegal_subscription_channel"
    runtime = {
        "dashboard_uid": context.dashboard_uid,
        "user_login": context.low_access_user_login,
        "channel": "sms",
    }
    before = capture_snapshot(scenario, runtime)
    http_steps: list[dict[str, Any]] = []
    intermediate: dict[str, Any] = {}
    anomalies: list[str] = []

    response, _ = DashboardHubService.create_subscription(
        dashboard_uid=context.dashboard_uid,
        user_login=context.low_access_user_login,
        channel="sms",
        cron="0 */6 * * *",
    )
    http_steps.append(_step("create_subscription_illegal_channel", response, 422))
    after = capture_snapshot(scenario, runtime)

    if response.status_code != 422:
        anomalies.append("unexpected_http_illegal_channel_status")
    if after.get("subscription", {}).get("business_key_count") not in (0, None):
        anomalies.append("mysql_subscription_created_for_illegal_channel")

    return _finalize_result(
        scenario=scenario,
        runtime=runtime,
        before=before,
        after=after,
        http_steps=http_steps,
        intermediate=intermediate,
        anomalies=anomalies,
    )


SCENARIO_RUNNERS = {
    "subscription_persistence": _run_subscription_persistence,
    "subscription_conflict": _run_subscription_conflict,
    "subscription_cache_invalidation": _run_subscription_cache_invalidation,
    "share_link_view_count": _run_share_link_view_count,
    "share_link_cache_invalidation": _run_share_link_cache_invalidation,
    "summary_cache": _run_summary_cache,
    "expired_share_link": _run_expired_share_link,
    "subscription_unknown_dashboard": _run_subscription_unknown_dashboard,
    "unknown_share_token": _run_unknown_share_token,
    "illegal_subscription_channel": _run_illegal_subscription_channel,
}


def run_standard_scenario(scenario: str, context: AgentEnvironmentContext) -> dict[str, Any]:
    runner = SCENARIO_RUNNERS.get(scenario)
    if runner is None:
        return {
            "scenario": scenario,
            "execution_error": f"unsupported scenario: {scenario}",
            "failure_reproduced": False,
            "http_steps": [],
            "intermediate": {},
            "anomalies": ["route_unsupported_scenario"],
            "snapshot": {"before": {}, "after": {}, "diff": {}},
            "runtime": {},
        }
    try:
        return runner(context)
    except Exception as exc:  # noqa: BLE001
        return {
            "scenario": scenario,
            "execution_error": str(exc),
            "failure_reproduced": False,
            "http_steps": [],
            "intermediate": {},
            "anomalies": ["route_scenario_execution_failed"],
            "snapshot": {"before": {}, "after": {}, "diff": {}},
            "runtime": {},
        }
