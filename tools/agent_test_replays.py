from __future__ import annotations

import json
from typing import Any, Callable
from uuid import uuid4

from data.dashboard_hub_data import make_share_link_payload, make_subscription_payload
from services.dashboard_hub_service import DashboardHubService
from services.mysql_service import MySQLService
from services.redis_service import RedisService
from tools.agent_environment import AgentEnvironmentContext
from tools.agent_evidence import build_summary_cache_key
from tools.agent_snapshot import capture_snapshot, diff_snapshots


ReplayHandler = Callable[[AgentEnvironmentContext], dict[str, Any]]


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


def _new_runtime(context: AgentEnvironmentContext, **extra: Any) -> dict[str, Any]:
    runtime: dict[str, Any] = {
        "replay_id": uuid4().hex,
        "dashboard_uid": context.dashboard_uid,
    }
    runtime.update(extra)
    return runtime


def _finalize_result(
    *,
    replay_target: str,
    runtime: dict[str, Any],
    before: dict[str, Any],
    after: dict[str, Any],
    http_steps: list[dict[str, Any]],
    intermediate: dict[str, Any],
    observations: list[str],
    execution_error: str | None = None,
) -> dict[str, Any]:
    return {
        "replay_target": replay_target,
        "runtime": runtime,
        "http_steps": http_steps,
        "intermediate": intermediate,
        "observations": observations,
        "failure_reproduced": bool(observations),
        "execution_error": execution_error,
        "snapshot": {
            "before": before,
            "after": after,
            "diff": diff_snapshots(before, after),
        },
    }


def _run_test_create_subscription_success(context: AgentEnvironmentContext) -> dict[str, Any]:
    replay_target = "test_create_subscription_success"
    runtime = _new_runtime(context, user_login=context.existing_user_login, channel="email")
    before = capture_snapshot(replay_target, runtime)
    http_steps: list[dict[str, Any]] = []
    intermediate: dict[str, Any] = {}
    observations: list[str] = []

    response, subscription_id = DashboardHubService.create_subscription(
        **make_subscription_payload(context.dashboard_uid, context.existing_user_login, channel="email"),
        replay_id=runtime["replay_id"],
    )
    runtime["subscription_id"] = subscription_id
    if subscription_id:
        context.register_subscription(subscription_id)
    http_steps.append(_step("create_subscription", response, 201))
    intermediate["response_payload"] = response.json() if response.status_code in {200, 201} else None
    after = capture_snapshot(replay_target, runtime)

    if response.status_code != 201:
        observations.append("obs_http_create_status_unexpected")
    sub_state = after.get("subscription", {})
    if sub_state.get("subscription_row") is None:
        observations.append("obs_db_subscription_row_absent_after_create")

    return _finalize_result(
        replay_target=replay_target,
        runtime=runtime,
        before=before,
        after=after,
        http_steps=http_steps,
        intermediate=intermediate,
        observations=observations,
    )


def _run_test_create_share_link_success(context: AgentEnvironmentContext) -> dict[str, Any]:
    replay_target = "test_create_share_link_success"
    runtime = _new_runtime(context)
    before = capture_snapshot(replay_target, runtime)
    http_steps: list[dict[str, Any]] = []
    intermediate: dict[str, Any] = {}
    observations: list[str] = []

    response, token = DashboardHubService.create_share_link(
        **make_share_link_payload(context.dashboard_uid),
        replay_id=runtime["replay_id"],
    )
    runtime["token"] = token
    if token:
        context.register_share_token(token)
    http_steps.append(_step("create_share_link", response, 201))
    intermediate["response_payload"] = response.json() if response.status_code in {200, 201} else None
    after = capture_snapshot(replay_target, runtime)

    if response.status_code != 201:
        observations.append("obs_http_create_status_unexpected")
    share_state = after.get("share_link", {})
    if share_state.get("mysql_row") is None:
        observations.append("obs_db_share_row_absent_after_create")

    return _finalize_result(
        replay_target=replay_target,
        runtime=runtime,
        before=before,
        after=after,
        http_steps=http_steps,
        intermediate=intermediate,
        observations=observations,
    )


def _run_test_get_subscriptions_success(context: AgentEnvironmentContext) -> dict[str, Any]:
    replay_target = "test_get_subscriptions_success"
    runtime = _new_runtime(context, user_login=context.existing_user_login, channel="slack")
    before = capture_snapshot(replay_target, runtime)
    http_steps = []
    intermediate: dict[str, Any] = {}
    observations: list[str] = []

    create_response, subscription_id = DashboardHubService.create_subscription(
        **make_subscription_payload(context.dashboard_uid, context.existing_user_login, channel="slack"),
        replay_id=runtime["replay_id"],
    )
    runtime["subscription_id"] = subscription_id
    if subscription_id:
        context.register_subscription(subscription_id)
    http_steps.append(_step("create_subscription", create_response, 201))

    list_response = DashboardHubService.list_subscriptions(context.dashboard_uid, replay_id=runtime["replay_id"])
    http_steps.append(_step("list_subscriptions", list_response, 200))
    intermediate["list_payload"] = list_response.json() if list_response.status_code == 200 else None
    after = capture_snapshot(replay_target, runtime)

    if create_response.status_code != 201:
        observations.append("obs_http_create_status_unexpected")
    if list_response.status_code != 200:
        observations.append("obs_http_list_status_unexpected")
    items = (intermediate.get("list_payload") or {}).get("items", [])
    if items and not any(item.get("id") == subscription_id for item in items):
        observations.append("obs_http_created_subscription_absent_from_list")

    return _finalize_result(
        replay_target=replay_target,
        runtime=runtime,
        before=before,
        after=after,
        http_steps=http_steps,
        intermediate=intermediate,
        observations=observations,
    )


def _run_test_get_share_link_success(context: AgentEnvironmentContext) -> dict[str, Any]:
    replay_target = "test_get_share_link_success"
    runtime = _new_runtime(context)
    before = capture_snapshot(replay_target, runtime)
    http_steps = []
    intermediate: dict[str, Any] = {}
    observations: list[str] = []

    create_response, token = DashboardHubService.create_share_link(
        **make_share_link_payload(context.dashboard_uid),
        replay_id=runtime["replay_id"],
    )
    runtime["token"] = token
    if token:
        context.register_share_token(token)
    http_steps.append(_step("create_share_link", create_response, 201))

    get_response = DashboardHubService.get_share_link(token, replay_id=runtime["replay_id"])
    http_steps.append(_step("get_share_link", get_response, 200))
    intermediate["response_payload"] = get_response.json() if get_response.status_code == 200 else None
    after = capture_snapshot(replay_target, runtime)

    if create_response.status_code != 201:
        observations.append("obs_http_create_status_unexpected")
    if get_response.status_code != 200:
        observations.append("obs_http_get_status_unexpected")

    return _finalize_result(
        replay_target=replay_target,
        runtime=runtime,
        before=before,
        after=after,
        http_steps=http_steps,
        intermediate=intermediate,
        observations=observations,
    )


def _run_test_get_dashboard_summary_success(context: AgentEnvironmentContext) -> dict[str, Any]:
    replay_target = "test_get_dashboard_summary_success"
    runtime = _new_runtime(context, summary_key=build_summary_cache_key(context.dashboard_uid))
    before = capture_snapshot(replay_target, runtime)
    http_steps = []
    intermediate: dict[str, Any] = {}
    observations: list[str] = []

    response = DashboardHubService.get_dashboard_summary(context.dashboard_uid, replay_id=runtime["replay_id"])
    http_steps.append(_step("get_dashboard_summary", response, 200))
    if response.status_code == 200:
        payload = response.json()
        runtime["summary_key"] = (
            f"dashhub:summary:{context.dashboard_uid}:{payload['provider']}:{payload['model']}:{payload['prompt_version']}"
        )
        intermediate["summary_response"] = payload
    after = capture_snapshot(replay_target, runtime)

    if response.status_code != 200:
        observations.append("obs_http_summary_status_unexpected")
    if intermediate.get("summary_response") and not intermediate["summary_response"].get("ai_summary"):
        observations.append("obs_summary_text_absent_after_read")

    return _finalize_result(
        replay_target=replay_target,
        runtime=runtime,
        before=before,
        after=after,
        http_steps=http_steps,
        intermediate=intermediate,
        observations=observations,
    )


def _run_test_create_subscription_with_unknown_dashboard(context: AgentEnvironmentContext) -> dict[str, Any]:
    replay_target = "test_create_subscription_with_unknown_dashboard"
    runtime = _new_runtime(context, dashboard_uid="not-exists-uid", user_login=context.existing_user_login, channel="email")
    before = capture_snapshot(replay_target, runtime)
    http_steps = []
    intermediate: dict[str, Any] = {}
    observations: list[str] = []

    response, _ = DashboardHubService.create_subscription(
        dashboard_uid="not-exists-uid",
        user_login=context.existing_user_login,
        channel="email",
        cron="0 */6 * * *",
        replay_id=runtime["replay_id"],
    )
    http_steps.append(_step("create_subscription_unknown_dashboard", response, 404))
    after = capture_snapshot(replay_target, runtime)

    if response.status_code != 404:
        observations.append("obs_http_unknown_dashboard_status_unexpected")
    if after.get("subscription", {}).get("business_key_count") not in (0, None):
        observations.append("obs_db_subscription_rows_present_after_unknown_dashboard_create")

    return _finalize_result(
        replay_target=replay_target,
        runtime=runtime,
        before=before,
        after=after,
        http_steps=http_steps,
        intermediate=intermediate,
        observations=observations,
    )


def _run_test_create_duplicate_subscription(context: AgentEnvironmentContext) -> dict[str, Any]:
    replay_target = "test_create_duplicate_subscription"
    runtime = _new_runtime(context, user_login=context.existing_user_login, channel="webhook")
    before = capture_snapshot(replay_target, runtime)
    http_steps = []
    intermediate: dict[str, Any] = {}
    observations: list[str] = []
    payload = make_subscription_payload(context.dashboard_uid, context.existing_user_login, channel="webhook")

    first_response, first_id = DashboardHubService.create_subscription(**payload, replay_id=runtime["replay_id"])
    runtime["subscription_id"] = first_id
    if first_id:
        context.register_subscription(first_id)
    http_steps.append(_step("create_subscription_first", first_response, 201))

    second_response, _ = DashboardHubService.create_subscription(**payload, replay_id=runtime["replay_id"])
    http_steps.append(_step("create_subscription_second", second_response, 409))
    after = capture_snapshot(replay_target, runtime)

    if first_response.status_code != 201:
        observations.append("obs_http_first_create_status_unexpected")
    if second_response.status_code != 409:
        observations.append("obs_http_second_create_status_unexpected")
    if after.get("subscription", {}).get("business_key_count") != 1:
        observations.append("obs_db_subscription_row_count_after_repeat_create")

    return _finalize_result(
        replay_target=replay_target,
        runtime=runtime,
        before=before,
        after=after,
        http_steps=http_steps,
        intermediate=intermediate,
        observations=observations,
    )


def _run_test_get_unknown_share_token(context: AgentEnvironmentContext) -> dict[str, Any]:
    replay_target = "test_get_unknown_share_token"
    runtime = _new_runtime(context, token="missing-token")
    before = capture_snapshot(replay_target, runtime)
    http_steps = []
    intermediate: dict[str, Any] = {}
    observations: list[str] = []

    response = DashboardHubService.get_share_link("missing-token", replay_id=runtime["replay_id"])
    http_steps.append(_step("get_unknown_share_token", response, 404))
    after = capture_snapshot(replay_target, runtime)

    if response.status_code != 404:
        observations.append("obs_http_unknown_share_status_unexpected")
    share_state = after.get("share_link", {})
    if share_state.get("mysql_row") is not None:
        observations.append("obs_db_share_row_present_after_unknown_token_read")
    if share_state.get("cache_exists"):
        observations.append("obs_cache_key_present_after_unknown_token_read")

    return _finalize_result(
        replay_target=replay_target,
        runtime=runtime,
        before=before,
        after=after,
        http_steps=http_steps,
        intermediate=intermediate,
        observations=observations,
    )


def _run_test_create_subscription_with_illegal_channel(context: AgentEnvironmentContext) -> dict[str, Any]:
    replay_target = "test_create_subscription_with_illegal_channel"
    runtime = _new_runtime(context, user_login=context.low_access_user_login, channel="sms")
    before = capture_snapshot(replay_target, runtime)
    http_steps = []
    intermediate: dict[str, Any] = {}
    observations: list[str] = []

    response, _ = DashboardHubService.create_subscription(
        dashboard_uid=context.dashboard_uid,
        user_login=context.low_access_user_login,
        channel="sms",
        cron="0 */6 * * *",
        replay_id=runtime["replay_id"],
    )
    http_steps.append(_step("create_subscription_invalid_channel", response, 422))
    after = capture_snapshot(replay_target, runtime)

    if response.status_code != 422:
        observations.append("obs_http_invalid_channel_status_unexpected")
    if after.get("subscription", {}).get("business_key_count") not in (0, None):
        observations.append("obs_db_subscription_rows_present_after_invalid_channel_create")

    return _finalize_result(
        replay_target=replay_target,
        runtime=runtime,
        before=before,
        after=after,
        http_steps=http_steps,
        intermediate=intermediate,
        observations=observations,
    )


def _run_test_get_expired_share_link(context: AgentEnvironmentContext) -> dict[str, Any]:
    replay_target = "test_get_expired_share_link"
    runtime = _new_runtime(context)
    before = capture_snapshot(replay_target, runtime)
    http_steps = []
    intermediate: dict[str, Any] = {}
    observations: list[str] = []

    create_response, token = DashboardHubService.create_share_link(
        **make_share_link_payload(context.dashboard_uid, ttl_hours=-1),
        replay_id=runtime["replay_id"],
    )
    runtime["token"] = token
    if token:
        context.register_share_token(token)
    http_steps.append(_step("create_expired_share_link", create_response, 201))

    get_response = DashboardHubService.get_share_link(token, replay_id=runtime["replay_id"])
    http_steps.append(_step("get_expired_share_link", get_response, 410))
    after = capture_snapshot(replay_target, runtime)

    if create_response.status_code != 201:
        observations.append("obs_http_create_status_unexpected")
    if get_response.status_code != 410:
        observations.append("obs_http_expired_read_status_unexpected")

    return _finalize_result(
        replay_target=replay_target,
        runtime=runtime,
        before=before,
        after=after,
        http_steps=http_steps,
        intermediate=intermediate,
        observations=observations,
    )


def _run_test_subscription_written_to_mysql(context: AgentEnvironmentContext) -> dict[str, Any]:
    replay_target = "test_subscription_written_to_mysql"
    runtime = _new_runtime(context, user_login=context.low_access_user_login, channel="slack")
    before = capture_snapshot(replay_target, runtime)
    http_steps = []
    intermediate: dict[str, Any] = {}
    observations: list[str] = []

    response, subscription_id = DashboardHubService.create_subscription(
        **make_subscription_payload(context.dashboard_uid, context.low_access_user_login, channel="slack"),
        replay_id=runtime["replay_id"],
    )
    runtime["subscription_id"] = subscription_id
    if subscription_id:
        context.register_subscription(subscription_id)
    http_steps.append(_step("create_subscription", response, 201))

    created_row = MySQLService.fetch_subscription_by_id(subscription_id) if subscription_id else None
    intermediate["db_row_after_create"] = created_row

    delete_response = DashboardHubService.delete_subscription(subscription_id, replay_id=runtime["replay_id"])
    http_steps.append(_step("delete_subscription", delete_response, 200))
    context.forget_subscription(subscription_id)
    after = capture_snapshot(replay_target, runtime)

    if response.status_code != 201:
        observations.append("obs_http_create_status_unexpected")
    if delete_response.status_code != 200:
        observations.append("obs_http_delete_status_unexpected")
    if created_row is None:
        observations.append("obs_db_subscription_row_absent_after_create")
    else:
        if created_row.get("dashboard_uid") != context.dashboard_uid:
            observations.append("obs_db_subscription_dashboard_uid_mismatch_after_create")
        if created_row.get("user_login") != context.low_access_user_login:
            observations.append("obs_db_subscription_user_login_mismatch_after_create")
        if created_row.get("channel") != "slack":
            observations.append("obs_db_subscription_channel_mismatch_after_create")
    if after.get("subscription", {}).get("subscription_row") is not None:
        observations.append("obs_db_subscription_row_present_after_delete")

    return _finalize_result(
        replay_target=replay_target,
        runtime=runtime,
        before=before,
        after=after,
        http_steps=http_steps,
        intermediate=intermediate,
        observations=observations,
    )


def _run_test_share_link_written_to_mysql_and_view_count_updated(context: AgentEnvironmentContext) -> dict[str, Any]:
    replay_target = "test_share_link_written_to_mysql_and_view_count_updated"
    runtime = _new_runtime(context)
    before = capture_snapshot(replay_target, runtime)
    http_steps = []
    intermediate: dict[str, Any] = {}
    observations: list[str] = []

    create_response, token = DashboardHubService.create_share_link(
        **make_share_link_payload(context.dashboard_uid),
        replay_id=runtime["replay_id"],
    )
    runtime["token"] = token
    if token:
        context.register_share_token(token)
    http_steps.append(_step("create_share_link", create_response, 201))

    row_after_create = MySQLService.fetch_share_link_by_token(token) if token else None
    intermediate["db_row_after_create"] = row_after_create

    get_response = DashboardHubService.get_share_link(token, replay_id=runtime["replay_id"])
    http_steps.append(_step("get_share_link", get_response, 200))

    row_after_get = MySQLService.fetch_share_link_by_token(token) if token else None
    intermediate["db_row_after_get"] = row_after_get

    delete_response = DashboardHubService.delete_share_link(token, replay_id=runtime["replay_id"])
    http_steps.append(_step("delete_share_link", delete_response, 200))
    context.forget_share_token(token)
    after = capture_snapshot(replay_target, runtime)

    if create_response.status_code != 201:
        observations.append("obs_http_create_status_unexpected")
    if get_response.status_code != 200:
        observations.append("obs_http_get_status_unexpected")
    if delete_response.status_code != 200:
        observations.append("obs_http_delete_status_unexpected")

    if row_after_create is None:
        observations.append("obs_db_share_row_absent_after_create")
    else:
        if row_after_create.get("dashboard_uid") != context.dashboard_uid:
            observations.append("obs_db_share_dashboard_uid_mismatch_after_create")
        if int(row_after_create.get("view_count", -1)) != 0:
            observations.append("obs_db_initial_view_count_unexpected")

    if row_after_get is None:
        observations.append("obs_db_share_row_absent_after_read")
    else:
        if int(row_after_get.get("view_count", 0)) < 1:
            observations.append("obs_db_view_count_not_advanced_after_read")

    if after.get("share_link", {}).get("mysql_row") is not None:
        observations.append("obs_db_share_row_present_after_delete")

    return _finalize_result(
        replay_target=replay_target,
        runtime=runtime,
        before=before,
        after=after,
        http_steps=http_steps,
        intermediate=intermediate,
        observations=observations,
    )


def _run_test_subscriptions_are_cached_and_invalidated(context: AgentEnvironmentContext) -> dict[str, Any]:
    replay_target = "test_subscriptions_are_cached_and_invalidated"
    runtime = _new_runtime(context, user_login=context.low_access_user_login, channel="webhook")
    before = capture_snapshot(replay_target, runtime)
    http_steps = []
    intermediate: dict[str, Any] = {}
    observations: list[str] = []

    create_response, subscription_id = DashboardHubService.create_subscription(
        **make_subscription_payload(context.dashboard_uid, context.low_access_user_login, channel="webhook"),
        replay_id=runtime["replay_id"],
    )
    runtime["subscription_id"] = subscription_id
    if subscription_id:
        context.register_subscription(subscription_id)
    http_steps.append(_step("create_subscription", create_response, 201))

    list_response = DashboardHubService.list_subscriptions(context.dashboard_uid, replay_id=runtime["replay_id"])
    http_steps.append(_step("list_subscriptions", list_response, 200))
    cache_key = f"dashhub:subscriptions:{context.dashboard_uid}"
    intermediate["cache_payload_after_list"] = RedisService.get_json(cache_key)

    delete_response = DashboardHubService.delete_subscription(subscription_id, replay_id=runtime["replay_id"])
    http_steps.append(_step("delete_subscription", delete_response, 200))
    context.forget_subscription(subscription_id)
    after = capture_snapshot(replay_target, runtime)

    if create_response.status_code != 201:
        observations.append("obs_http_create_status_unexpected")
    if list_response.status_code != 200:
        observations.append("obs_http_list_status_unexpected")
    if delete_response.status_code != 200:
        observations.append("obs_http_delete_status_unexpected")
    if intermediate["cache_payload_after_list"] is None:
        observations.append("obs_cache_subscription_payload_absent_after_list")
    if after.get("subscription", {}).get("cache_exists"):
        observations.append("obs_cache_subscription_key_present_after_delete")
    if after.get("subscription", {}).get("business_key_count") not in (0, None):
        observations.append("obs_db_subscription_rows_present_after_delete")

    return _finalize_result(
        replay_target=replay_target,
        runtime=runtime,
        before=before,
        after=after,
        http_steps=http_steps,
        intermediate=intermediate,
        observations=observations,
    )


def _run_test_share_link_is_cached_and_invalidated(context: AgentEnvironmentContext) -> dict[str, Any]:
    replay_target = "test_share_link_is_cached_and_invalidated"
    runtime = _new_runtime(context)
    before = capture_snapshot(replay_target, runtime)
    http_steps = []
    intermediate: dict[str, Any] = {}
    observations: list[str] = []

    create_response, token = DashboardHubService.create_share_link(
        **make_share_link_payload(context.dashboard_uid),
        replay_id=runtime["replay_id"],
    )
    runtime["token"] = token
    if token:
        context.register_share_token(token)
    http_steps.append(_step("create_share_link", create_response, 201))

    get_response = DashboardHubService.get_share_link(token, replay_id=runtime["replay_id"])
    http_steps.append(_step("get_share_link", get_response, 200))
    cache_key = f"dashhub:share:{token}"
    intermediate["cache_payload_after_read"] = RedisService.get_json(cache_key)

    delete_response = DashboardHubService.delete_share_link(token, replay_id=runtime["replay_id"])
    http_steps.append(_step("delete_share_link", delete_response, 200))
    context.forget_share_token(token)
    after = capture_snapshot(replay_target, runtime)

    if create_response.status_code != 201:
        observations.append("obs_http_create_status_unexpected")
    if get_response.status_code != 200:
        observations.append("obs_http_get_status_unexpected")
    if delete_response.status_code != 200:
        observations.append("obs_http_delete_status_unexpected")
    if intermediate["cache_payload_after_read"] is None:
        observations.append("obs_cache_share_payload_absent_after_read")
    if after.get("share_link", {}).get("cache_exists"):
        observations.append("obs_cache_share_key_present_after_delete")
    if after.get("share_link", {}).get("mysql_row") is not None:
        observations.append("obs_db_share_row_present_after_delete")

    return _finalize_result(
        replay_target=replay_target,
        runtime=runtime,
        before=before,
        after=after,
        http_steps=http_steps,
        intermediate=intermediate,
        observations=observations,
    )


def _run_test_dashboard_summary_is_cached(context: AgentEnvironmentContext) -> dict[str, Any]:
    replay_target = "test_dashboard_summary_is_cached"
    runtime = _new_runtime(context, summary_key=build_summary_cache_key(context.dashboard_uid))
    before = capture_snapshot(replay_target, runtime)
    http_steps = []
    intermediate: dict[str, Any] = {}
    observations: list[str] = []

    response = DashboardHubService.get_dashboard_summary(context.dashboard_uid, replay_id=runtime["replay_id"])
    http_steps.append(_step("get_dashboard_summary", response, 200))
    if response.status_code == 200:
        payload = response.json()
        runtime["summary_key"] = (
            f"dashhub:summary:{context.dashboard_uid}:{payload['provider']}:{payload['model']}:{payload['prompt_version']}"
        )
        intermediate["summary_response"] = payload
    after = capture_snapshot(replay_target, runtime)

    if response.status_code != 200:
        observations.append("obs_http_summary_status_unexpected")
    summary_state = after.get("summary", {})
    if not summary_state.get("cache_exists"):
        observations.append("obs_cache_summary_key_absent_after_read")
    if intermediate.get("summary_response") and summary_state.get("cache_payload"):
        cached_payload = summary_state["cache_payload"]
        if cached_payload.get("ai_summary") != intermediate["summary_response"].get("ai_summary"):
            observations.append("obs_summary_payload_mismatch_after_read")
        if intermediate["summary_response"].get("source") not in {"ai", "fallback"}:
            observations.append("obs_summary_source_value_unexpected")

    return _finalize_result(
        replay_target=replay_target,
        runtime=runtime,
        before=before,
        after=after,
        http_steps=http_steps,
        intermediate=intermediate,
        observations=observations,
    )


TEST_REPLAY_HANDLERS: dict[str, ReplayHandler] = {
    "test_create_subscription_success": _run_test_create_subscription_success,
    "test_create_share_link_success": _run_test_create_share_link_success,
    "test_get_subscriptions_success": _run_test_get_subscriptions_success,
    "test_get_share_link_success": _run_test_get_share_link_success,
    "test_get_dashboard_summary_success": _run_test_get_dashboard_summary_success,
    "test_create_subscription_with_unknown_dashboard": _run_test_create_subscription_with_unknown_dashboard,
    "test_create_duplicate_subscription": _run_test_create_duplicate_subscription,
    "test_get_unknown_share_token": _run_test_get_unknown_share_token,
    "test_create_subscription_with_illegal_channel": _run_test_create_subscription_with_illegal_channel,
    "test_get_expired_share_link": _run_test_get_expired_share_link,
    "test_subscription_written_to_mysql": _run_test_subscription_written_to_mysql,
    "test_share_link_written_to_mysql_and_view_count_updated": _run_test_share_link_written_to_mysql_and_view_count_updated,
    "test_subscriptions_are_cached_and_invalidated": _run_test_subscriptions_are_cached_and_invalidated,
    "test_share_link_is_cached_and_invalidated": _run_test_share_link_is_cached_and_invalidated,
    "test_dashboard_summary_is_cached": _run_test_dashboard_summary_is_cached,
}


def run_failed_test_replay(test_name: str, context: AgentEnvironmentContext) -> dict[str, Any]:
    handler = TEST_REPLAY_HANDLERS.get(test_name)
    if handler is None:
        return {
            "replay_target": test_name,
            "execution_error": f"unsupported failed test replay: {test_name}",
            "failure_reproduced": False,
            "http_steps": [],
            "intermediate": {},
            "observations": ["replay_unsupported_test"],
            "snapshot": {"before": {}, "after": {}, "diff": {}},
            "runtime": {},
        }
    try:
        return handler(context)
    except Exception as exc:  # noqa: BLE001
        return {
            "replay_target": test_name,
            "execution_error": str(exc),
            "failure_reproduced": False,
            "http_steps": [],
            "intermediate": {},
            "observations": ["replay_execution_failed"],
            "snapshot": {"before": {}, "after": {}, "diff": {}},
            "runtime": {},
        }
