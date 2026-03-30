from __future__ import annotations

from typing import Any


REQUEST_VALIDATION = "request_validation"
MAIN_STATE_WRITE = "main_state_write"
MAIN_STATE_DELETE = "main_state_delete"
LIST_PAYLOAD_CONSISTENCY = "list_payload_consistency"
CACHE_FILL_AFTER_READ = "cache_fill_after_read"
CACHE_INVALIDATION_AFTER_DELETE = "cache_invalidation_after_delete"
SHARE_READ_CONSISTENCY = "share_read_consistency"
SUMMARY_GENERATION = "summary_generation"
SUMMARY_CACHE_WRITE = "summary_cache_write"
NEGATIVE_SIDE_EFFECT_ABSENCE = "negative_side_effect_absence"
REPLAY_EXECUTION = "replay_execution"


_STAGE_SCOPE = {
    REQUEST_VALIDATION: (["请求接收与参数校验段"], [
        "检查接口入参、鉴权与状态码分支是否按预期返回。",
        "核对服务端结构化日志中的 started/finished/error 事件是否完整。",
    ]),
    MAIN_STATE_WRITE: (["主状态写入段", "写入后的持久化一致性检查段"], [
        "检查写库语句是否真正提交，以及关键字段是否与请求一致。",
        "核对写入成功后的结构化日志和数据库实际记录是否一致。",
    ]),
    MAIN_STATE_DELETE: (["主状态删除段", "删除提交后的持久化一致性检查段"], [
        "检查删除逻辑是否真正执行到 db.commit 之后。",
        "核对删除后主记录是否仍残留，以及是否存在提前 return 或吞异常。",
    ]),
    LIST_PAYLOAD_CONSISTENCY: (["订阅列表读取结果构造段"], [
        "检查列表查询结果构造是否漏掉刚创建的主记录。",
        "核对过滤条件、排序逻辑和返回 payload 组装逻辑。",
    ]),
    CACHE_FILL_AFTER_READ: (["读取后的缓存写入段"], [
        "检查读取成功后是否执行缓存写入。",
        "核对 cache key 计算与 payload 结构是否正确。",
    ]),
    CACHE_INVALIDATION_AFTER_DELETE: (["删除后的缓存失效段"], [
        "检查 delete 成功后是否执行 cache.delete。",
        "核对删除路径中的 cache invalidated 结构化日志是否缺失。",
        "检查删除路径是否在删缓存前提前结束。",
    ]),
    SHARE_READ_CONSISTENCY: (["分享链接读取与 view_count 更新段"], [
        "检查分享链接读取后 view_count 是否更新并提交。",
        "核对缓存命中路径和回源路径下的 view_count 更新是否一致。",
    ]),
    SUMMARY_GENERATION: (["摘要生成段"], [
        "检查摘要生成路径是否返回 ai_summary，以及 source/provider/model 是否合理。",
        "核对 AI 或 fallback 分支日志与最终返回 payload 是否一致。",
    ]),
    SUMMARY_CACHE_WRITE: (["摘要读取后的缓存写入段"], [
        "检查摘要读取成功后是否执行 summary cache 写入。",
        "核对 summary cache key 与 payload 内容是否一致。",
    ]),
    NEGATIVE_SIDE_EFFECT_ABSENCE: (["负向请求后的无副作用保障段"], [
        "检查负向请求返回错误后是否仍误写数据库或缓存。",
        "核对错误分支里是否存在多余副作用动作。",
    ]),
    REPLAY_EXECUTION: (["agent 重放执行段"], [
        "先确认该失败是否属于当前已支持的失败用例重放范围。",
        "检查 agent 重放环境、测试数据准备和清理流程。",
    ]),
}


SUCCESS_STYLE_TARGETS = {
    "test_create_subscription_success",
    "test_create_share_link_success",
    "test_get_subscriptions_success",
    "test_get_share_link_success",
    "test_get_dashboard_summary_success",
    "test_subscription_written_to_mysql",
    "test_share_link_written_to_mysql_and_view_count_updated",
    "test_subscriptions_are_cached_and_invalidated",
    "test_share_link_is_cached_and_invalidated",
    "test_dashboard_summary_is_cached",
}

NEGATIVE_STYLE_TARGETS = {
    "test_create_subscription_with_unknown_dashboard",
    "test_create_subscription_with_illegal_channel",
    "test_get_unknown_share_token",
    "test_get_expired_share_link",
    "test_create_duplicate_subscription",
}


def _present(value: Any) -> bool:
    return value is not None


def _status_map(http_steps: list[dict[str, Any]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for step in http_steps:
        name = step.get("step")
        if not name:
            continue
        try:
            result[str(name)] = int(step.get("status_code", 0))
        except Exception:
            continue
    return result


def _expected_map(http_steps: list[dict[str, Any]]) -> dict[str, Any]:
    return {str(step.get("step")): step.get("expected_status") for step in http_steps if step.get("step")}


def _matches_expected(status_code: Any, expected_status: Any) -> bool:
    if expected_status is None:
        return True
    if isinstance(expected_status, tuple):
        return status_code in expected_status
    return status_code == expected_status


def _log_events(snapshot: dict[str, Any]) -> set[str]:
    items = snapshot.get("after", {}).get("service_logs", {}).get("items", []) or []
    events: set[str] = set()
    for item in items:
        event = item.get("event")
        if isinstance(event, str) and event:
            events.add(event)
    return events


def _bool_text(flag: bool | None, yes: str, no: str) -> str | None:
    if flag is True:
        return yes
    if flag is False:
        return no
    return None


def _filtered_texts(*items: str | None) -> list[str]:
    return [item for item in items if item]


def _first_failed(stages: list[tuple[str, bool]]) -> str | None:
    for name, ok in stages:
        if not ok:
            return name
    return None


def _scope(stage: str | None) -> tuple[list[str], list[str]]:
    return _STAGE_SCOPE.get(stage or "", ([], []))


def _result(
    *,
    facts: dict[str, Any],
    stages: list[tuple[str, bool]],
    reproduced_original_failure: bool,
    chain_status: str,
    suspected_segment: str | None,
    confirmed_facts: list[str],
    excluded_scope: list[str],
) -> dict[str, Any]:
    first_abnormal_stage = _first_failed(stages)
    remaining_scope, manual_checks = _scope(first_abnormal_stage)
    return {
        "facts": facts,
        "stage_results": {name: ok for name, ok in stages},
        "reproduced_original_failure": reproduced_original_failure,
        "chain_status": chain_status,
        "first_abnormal_stage": first_abnormal_stage,
        "suspected_segment": suspected_segment if first_abnormal_stage else None,
        "confirmed_facts": confirmed_facts,
        "excluded_scope": excluded_scope,
        "remaining_scope": remaining_scope,
        "manual_checks": manual_checks,
    }


def _extract_facts(replay_result: dict[str, Any]) -> dict[str, Any]:
    http_steps = replay_result.get("http_steps", []) or []
    snapshot = replay_result.get("snapshot", {}) or {}
    intermediate = replay_result.get("intermediate", {}) or {}
    runtime = replay_result.get("runtime", {}) or {}
    after = snapshot.get("after", {}) or {}
    log_events = _log_events(snapshot)

    status_map = _status_map(http_steps)
    expected_map = _expected_map(http_steps)

    facts: dict[str, Any] = {}
    if isinstance(replay_result.get("facts"), dict):
        facts.update(replay_result["facts"])

    facts.update({
        "status_by_step": status_map,
        "expected_by_step": expected_map,
        "service_log_events": sorted(log_events),
        "create_status": status_map.get("create_subscription") or status_map.get("create_share_link"),
        "list_status": status_map.get("list_subscriptions"),
        "get_status": status_map.get("get_share_link"),
        "summary_status": status_map.get("get_dashboard_summary"),
        "delete_status": status_map.get("delete_subscription") or status_map.get("delete_share_link"),
        "first_create_status": status_map.get("create_subscription_first"),
        "second_create_status": status_map.get("create_subscription_second"),
        "unknown_dashboard_status": status_map.get("create_subscription_unknown_dashboard"),
        "invalid_channel_status": status_map.get("create_subscription_invalid_channel"),
        "unknown_share_status": status_map.get("get_unknown_share_token"),
        "expired_share_status": status_map.get("get_expired_share_link"),
    })

    subscription_after = after.get("subscription", {}) or {}
    share_after = after.get("share_link", {}) or {}
    summary_after = after.get("summary", {}) or {}

    facts.update({
        "subscription_business_key_count_after": subscription_after.get("business_key_count"),
        "subscription_row_after_present": _present(subscription_after.get("subscription_row")),
        "subscription_cache_exists_after": subscription_after.get("cache_exists"),
        "share_row_after_present": _present(share_after.get("mysql_row")),
        "share_cache_exists_after": share_after.get("cache_exists"),
        "summary_cache_exists_after": summary_after.get("cache_exists"),
        "summary_cache_payload_after_present": _present(summary_after.get("cache_payload")),
        "cache_payload_after_list_present": _present(intermediate.get("cache_payload_after_list")),
        "cache_payload_after_read_present": _present(intermediate.get("cache_payload_after_read")),
        "list_payload_present": _present(intermediate.get("list_payload")),
        "db_row_after_create_present": _present(intermediate.get("db_row_after_create")),
        "db_row_after_get_present": _present(intermediate.get("db_row_after_get")),
        "summary_response_present": _present(intermediate.get("summary_response")),
        "service_log_cache_invalidated_seen": any("cache" in event and ("invalid" in event or "delete" in event) for event in log_events),
    })

    list_payload = intermediate.get("list_payload") or {}
    subscription_id = runtime.get("subscription_id")
    if subscription_id is not None and isinstance(list_payload, dict):
        items = list_payload.get("items", []) or []
        facts["created_subscription_present_in_list"] = any(item.get("id") == subscription_id for item in items)

    created_row = intermediate.get("db_row_after_create") or {}
    row_after_get = intermediate.get("db_row_after_get") or {}
    if created_row:
        facts["db_row_after_create_dashboard_uid_matches"] = created_row.get("dashboard_uid") == runtime.get("dashboard_uid")
        facts["db_row_after_create_user_login_matches"] = created_row.get("user_login") == runtime.get("user_login")
        facts["db_row_after_create_channel_matches"] = created_row.get("channel") == runtime.get("channel")
        facts["share_row_after_create_dashboard_uid_matches"] = created_row.get("dashboard_uid") == runtime.get("dashboard_uid")
        try:
            facts["share_row_initial_view_count_zero"] = int(created_row.get("view_count", -1)) == 0
        except Exception:
            facts["share_row_initial_view_count_zero"] = False
    if row_after_get:
        try:
            facts["share_row_view_count_advanced_after_get"] = int(row_after_get.get("view_count", 0)) >= 1
        except Exception:
            facts["share_row_view_count_advanced_after_get"] = False

    summary_response = intermediate.get("summary_response") or {}
    summary_cache_payload = summary_after.get("cache_payload") or {}
    if summary_response and summary_cache_payload:
        facts["summary_payload_matches_after_read"] = summary_cache_payload.get("ai_summary") == summary_response.get("ai_summary")
    else:
        facts["summary_payload_matches_after_read"] = None
    if summary_response:
        facts["summary_source_valid"] = summary_response.get("source") in {"ai", "fallback"}

    return facts


def _preflight_failure(replay_result: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any] | None:
    execution_error = replay_result.get("execution_error")
    if execution_error:
        return {
            "facts": facts,
            "stage_results": {},
            "reproduced_original_failure": False,
            "chain_status": "interrupted",
            "first_abnormal_stage": REPLAY_EXECUTION,
            "suspected_segment": "agent replay execution",
            "confirmed_facts": [f"重放执行异常：{execution_error}"],
            "excluded_scope": [],
            "remaining_scope": ["agent 重放执行段"],
            "manual_checks": list(_STAGE_SCOPE[REPLAY_EXECUTION][1]),
        }
    return None


def _status_fact(facts: dict[str, Any], key: str, label: str) -> str | None:
    value = facts.get(key)
    if value is None:
        return None
    return f"{label}返回 {value}"


def _analyze_subscriptions_are_cached_and_invalidated(facts: dict[str, Any]) -> dict[str, Any]:
    create_ok = facts.get("create_status") == 201
    list_ok = facts.get("list_status") == 200
    cache_fill_ok = facts.get("cache_payload_after_list_present") is True
    delete_ok = facts.get("delete_status") == 200
    db_delete_ok = facts.get("subscription_business_key_count_after") == 0
    cache_invalidated_ok = facts.get("subscription_cache_exists_after") is False

    stages = [
        (MAIN_STATE_WRITE, create_ok),
        (CACHE_FILL_AFTER_READ, list_ok and cache_fill_ok),
        (MAIN_STATE_DELETE, delete_ok and db_delete_ok),
        (CACHE_INVALIDATION_AFTER_DELETE, cache_invalidated_ok),
    ]

    reproduced = bool(create_ok and list_ok and cache_fill_ok and delete_ok and db_delete_ok and facts.get("subscription_cache_exists_after") is True)
    chain_status = "interrupted" if (not create_ok or not list_ok or not delete_ok) else "complete"
    excluded = _filtered_texts(
        "创建订阅接口已按预期成功" if create_ok else None,
        "订阅列表读取已按预期成功" if list_ok else None,
        "列表读取后缓存已建立" if cache_fill_ok else None,
        "删除订阅接口已按预期成功" if delete_ok else None,
        "删除后数据库业务记录已清除" if db_delete_ok else None,
    )
    confirmed = _filtered_texts(
        _status_fact(facts, "create_status", "创建订阅"),
        _status_fact(facts, "list_status", "查询订阅列表"),
        _bool_text(facts.get("cache_payload_after_list_present"), "查询后 Redis 中已出现订阅列表缓存", "查询后 Redis 中未出现订阅列表缓存"),
        _status_fact(facts, "delete_status", "删除订阅"),
        f"删除后业务键对应记录数为 {facts.get('subscription_business_key_count_after')}" if facts.get("subscription_business_key_count_after") is not None else None,
        _bool_text(facts.get("subscription_cache_exists_after"), "删除后 Redis key 仍存在", "删除后 Redis key 已消失"),
    )
    return _result(
        facts=facts,
        stages=stages,
        reproduced_original_failure=reproduced,
        chain_status=chain_status,
        suspected_segment="subscription delete post-action cache invalidation",
        confirmed_facts=confirmed,
        excluded_scope=excluded,
    )


def _analyze_share_link_is_cached_and_invalidated(facts: dict[str, Any]) -> dict[str, Any]:
    create_ok = facts.get("create_status") == 201
    get_ok = facts.get("get_status") == 200
    cache_fill_ok = facts.get("cache_payload_after_read_present") is True
    delete_ok = facts.get("delete_status") == 200
    db_delete_ok = facts.get("share_row_after_present") is False
    cache_invalidated_ok = facts.get("share_cache_exists_after") is False

    stages = [
        (MAIN_STATE_WRITE, create_ok),
        (CACHE_FILL_AFTER_READ, get_ok and cache_fill_ok),
        (MAIN_STATE_DELETE, delete_ok and db_delete_ok),
        (CACHE_INVALIDATION_AFTER_DELETE, cache_invalidated_ok),
    ]
    reproduced = bool(create_ok and get_ok and cache_fill_ok and delete_ok and db_delete_ok and facts.get("share_cache_exists_after") is True)
    chain_status = "interrupted" if (not create_ok or not get_ok or not delete_ok) else "complete"
    excluded = _filtered_texts(
        "创建分享链接接口已按预期成功" if create_ok else None,
        "读取分享链接接口已按预期成功" if get_ok else None,
        "读取后缓存已建立" if cache_fill_ok else None,
        "删除分享链接接口已按预期成功" if delete_ok else None,
        "删除后数据库主记录已清除" if db_delete_ok else None,
    )
    confirmed = _filtered_texts(
        _status_fact(facts, "create_status", "创建分享链接"),
        _status_fact(facts, "get_status", "读取分享链接"),
        _bool_text(facts.get("cache_payload_after_read_present"), "读取后 Redis 中已出现分享链接缓存", "读取后 Redis 中未出现分享链接缓存"),
        _status_fact(facts, "delete_status", "删除分享链接"),
        _bool_text(facts.get("share_row_after_present"), "删除后数据库中仍存在分享链接记录", "删除后数据库中已不存在分享链接记录"),
        _bool_text(facts.get("share_cache_exists_after"), "删除后 Redis key 仍存在", "删除后 Redis key 已消失"),
    )
    return _result(
        facts=facts,
        stages=stages,
        reproduced_original_failure=reproduced,
        chain_status=chain_status,
        suspected_segment="share link delete post-action cache invalidation",
        confirmed_facts=confirmed,
        excluded_scope=excluded,
    )


def _analyze_dashboard_summary_is_cached(facts: dict[str, Any]) -> dict[str, Any]:
    summary_ok = facts.get("summary_status") == 200
    generated_ok = facts.get("summary_response_present") is True and facts.get("summary_source_valid") is not False
    cache_write_ok = facts.get("summary_cache_exists_after") is True and facts.get("summary_payload_matches_after_read") is not False
    stages = [
        (SUMMARY_GENERATION, summary_ok and generated_ok),
        (SUMMARY_CACHE_WRITE, cache_write_ok),
    ]
    reproduced = bool(summary_ok and generated_ok and ((facts.get("summary_cache_exists_after") is False) or (facts.get("summary_payload_matches_after_read") is False) or (facts.get("summary_source_valid") is False)))
    chain_status = "interrupted" if not summary_ok else "complete"
    excluded = _filtered_texts(
        "摘要读取接口已按预期成功" if summary_ok else None,
        "摘要响应已生成" if generated_ok else None,
    )
    confirmed = _filtered_texts(
        _status_fact(facts, "summary_status", "获取摘要"),
        _bool_text(facts.get("summary_response_present"), "摘要响应已生成", "摘要响应未生成"),
        _bool_text(facts.get("summary_cache_exists_after"), "摘要缓存已写入", "摘要缓存未写入"),
        _bool_text(facts.get("summary_payload_matches_after_read"), "缓存中的摘要内容与响应一致", "缓存中的摘要内容与响应不一致"),
        _bool_text(facts.get("summary_source_valid"), "摘要 source 字段取值正常", "摘要 source 字段取值异常"),
    )
    return _result(
        facts=facts,
        stages=stages,
        reproduced_original_failure=reproduced,
        chain_status=chain_status,
        suspected_segment="summary read cache persistence",
        confirmed_facts=confirmed,
        excluded_scope=excluded,
    )


def _analyze_subscription_written_to_mysql(facts: dict[str, Any]) -> dict[str, Any]:
    create_ok = facts.get("create_status") == 201
    write_ok = all(
        facts.get(key) is True for key in (
            "db_row_after_create_present",
            "db_row_after_create_dashboard_uid_matches",
            "db_row_after_create_user_login_matches",
            "db_row_after_create_channel_matches",
        )
    )
    delete_ok = facts.get("delete_status") == 200
    delete_persist_ok = facts.get("subscription_row_after_present") is False
    stages = [
        (MAIN_STATE_WRITE, create_ok and write_ok),
        (MAIN_STATE_DELETE, delete_ok and delete_persist_ok),
    ]
    reproduced = bool(create_ok and delete_ok and (not write_ok or not delete_persist_ok))
    chain_status = "interrupted" if (not create_ok or not delete_ok) else "complete"
    excluded = _filtered_texts(
        "创建订阅接口已按预期成功" if create_ok else None,
        "删除订阅接口已按预期成功" if delete_ok else None,
        "创建后已查询到订阅持久化记录" if facts.get("db_row_after_create_present") is True else None,
        "删除后主记录已清除" if delete_persist_ok else None,
    )
    confirmed = _filtered_texts(
        _status_fact(facts, "create_status", "创建订阅"),
        _bool_text(facts.get("db_row_after_create_present"), "创建后已查到订阅数据库记录", "创建后未查到订阅数据库记录"),
        _bool_text(facts.get("db_row_after_create_dashboard_uid_matches"), "dashboard_uid 与请求一致", "dashboard_uid 与请求不一致"),
        _bool_text(facts.get("db_row_after_create_user_login_matches"), "user_login 与请求一致", "user_login 与请求不一致"),
        _bool_text(facts.get("db_row_after_create_channel_matches"), "channel 与请求一致", "channel 与请求不一致"),
        _status_fact(facts, "delete_status", "删除订阅"),
        _bool_text(facts.get("subscription_row_after_present"), "删除后数据库中仍存在订阅记录", "删除后数据库中已不存在订阅记录"),
    )
    return _result(
        facts=facts,
        stages=stages,
        reproduced_original_failure=reproduced,
        chain_status=chain_status,
        suspected_segment="subscription persistence",
        confirmed_facts=confirmed,
        excluded_scope=excluded,
    )


def _analyze_share_link_written_to_mysql_and_view_count_updated(facts: dict[str, Any]) -> dict[str, Any]:
    create_ok = facts.get("create_status") == 201
    write_ok = all(
        facts.get(key) is True for key in (
            "db_row_after_create_present",
            "share_row_after_create_dashboard_uid_matches",
            "share_row_initial_view_count_zero",
        )
    )
    read_ok = facts.get("get_status") == 200 and facts.get("share_row_view_count_advanced_after_get") is True
    delete_ok = facts.get("delete_status") == 200 and facts.get("share_row_after_present") is False
    stages = [
        (MAIN_STATE_WRITE, create_ok and write_ok),
        (SHARE_READ_CONSISTENCY, read_ok),
        (MAIN_STATE_DELETE, delete_ok),
    ]
    reproduced = bool(create_ok and facts.get("get_status") == 200 and facts.get("delete_status") == 200 and (not write_ok or not read_ok or not delete_ok))
    chain_status = "interrupted" if (not create_ok or facts.get("get_status") != 200 or facts.get("delete_status") != 200) else "complete"
    excluded = _filtered_texts(
        "创建分享链接接口已按预期成功" if create_ok else None,
        "读取分享链接接口已按预期成功" if facts.get("get_status") == 200 else None,
        "删除分享链接接口已按预期成功" if facts.get("delete_status") == 200 else None,
    )
    confirmed = _filtered_texts(
        _status_fact(facts, "create_status", "创建分享链接"),
        _bool_text(facts.get("db_row_after_create_present"), "创建后已查到分享链接数据库记录", "创建后未查到分享链接数据库记录"),
        _bool_text(facts.get("share_row_after_create_dashboard_uid_matches"), "创建后 dashboard_uid 与请求一致", "创建后 dashboard_uid 与请求不一致"),
        _bool_text(facts.get("share_row_initial_view_count_zero"), "初始 view_count 为 0", "初始 view_count 不为 0"),
        _status_fact(facts, "get_status", "读取分享链接"),
        _bool_text(facts.get("share_row_view_count_advanced_after_get"), "读取后 view_count 已增长", "读取后 view_count 未增长"),
        _status_fact(facts, "delete_status", "删除分享链接"),
        _bool_text(facts.get("share_row_after_present"), "删除后数据库中仍存在分享链接记录", "删除后数据库中已不存在分享链接记录"),
    )
    return _result(
        facts=facts,
        stages=stages,
        reproduced_original_failure=reproduced,
        chain_status=chain_status,
        suspected_segment="share link persistence and read consistency",
        confirmed_facts=confirmed,
        excluded_scope=excluded,
    )


def _analyze_get_subscriptions_success(facts: dict[str, Any]) -> dict[str, Any]:
    create_ok = facts.get("create_status") == 201
    list_ok = facts.get("list_status") == 200
    payload_ok = facts.get("created_subscription_present_in_list") is True
    stages = [
        (MAIN_STATE_WRITE, create_ok),
        (LIST_PAYLOAD_CONSISTENCY, list_ok and payload_ok),
    ]
    reproduced = bool(create_ok and list_ok and facts.get("created_subscription_present_in_list") is False)
    chain_status = "interrupted" if (not create_ok or not list_ok) else "complete"
    excluded = _filtered_texts(
        "创建订阅接口已按预期成功" if create_ok else None,
        "查询订阅列表接口已按预期成功" if list_ok else None,
    )
    confirmed = _filtered_texts(
        _status_fact(facts, "create_status", "创建订阅"),
        _status_fact(facts, "list_status", "查询订阅列表"),
        _bool_text(facts.get("created_subscription_present_in_list"), "新建订阅已出现在列表中", "新建订阅未出现在列表中"),
    )
    return _result(
        facts=facts,
        stages=stages,
        reproduced_original_failure=reproduced,
        chain_status=chain_status,
        suspected_segment="subscription list payload composition",
        confirmed_facts=confirmed,
        excluded_scope=excluded,
    )


def _analyze_generic_success_case(replay_result: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    target = replay_result.get("replay_target")
    if target == "test_create_subscription_success":
        create_ok = facts.get("create_status") == 201
        persist_ok = facts.get("subscription_row_after_present") is True
        stages = [(MAIN_STATE_WRITE, create_ok and persist_ok)]
        reproduced = bool(create_ok and not persist_ok)
        chain_status = "interrupted" if not create_ok else "complete"
        confirmed = _filtered_texts(
            _status_fact(facts, "create_status", "创建订阅"),
            _bool_text(facts.get("subscription_row_after_present"), "创建后快照中已看到订阅记录", "创建后快照中未看到订阅记录"),
        )
        excluded = _filtered_texts("创建订阅接口已按预期成功" if create_ok else None)
        suspected = "subscription create persistence"
    elif target == "test_create_share_link_success":
        create_ok = facts.get("create_status") == 201
        persist_ok = facts.get("share_row_after_present") is True
        stages = [(MAIN_STATE_WRITE, create_ok and persist_ok)]
        reproduced = bool(create_ok and not persist_ok)
        chain_status = "interrupted" if not create_ok else "complete"
        confirmed = _filtered_texts(
            _status_fact(facts, "create_status", "创建分享链接"),
            _bool_text(facts.get("share_row_after_present"), "创建后快照中已看到分享链接记录", "创建后快照中未看到分享链接记录"),
        )
        excluded = _filtered_texts("创建分享链接接口已按预期成功" if create_ok else None)
        suspected = "share link create persistence"
    elif target == "test_get_share_link_success":
        create_ok = facts.get("create_status") == 201
        get_ok = facts.get("get_status") == 200
        stages = [(MAIN_STATE_WRITE, create_ok), (SHARE_READ_CONSISTENCY, get_ok)]
        reproduced = False
        chain_status = "interrupted" if (not create_ok or not get_ok) else "complete"
        confirmed = _filtered_texts(
            _status_fact(facts, "create_status", "创建分享链接"),
            _status_fact(facts, "get_status", "读取分享链接"),
        )
        excluded = _filtered_texts(
            "创建分享链接接口已按预期成功" if create_ok else None,
            "读取分享链接接口已按预期成功" if get_ok else None,
        )
        suspected = "share link read"
    elif target == "test_get_dashboard_summary_success":
        summary_ok = facts.get("summary_status") == 200
        generated_ok = facts.get("summary_response_present") is True
        stages = [(SUMMARY_GENERATION, summary_ok and generated_ok)]
        reproduced = bool(summary_ok and not generated_ok)
        chain_status = "interrupted" if not summary_ok else "complete"
        confirmed = _filtered_texts(
            _status_fact(facts, "summary_status", "获取摘要"),
            _bool_text(facts.get("summary_response_present"), "摘要响应已生成", "摘要响应未生成"),
        )
        excluded = _filtered_texts("摘要读取接口已按预期成功" if summary_ok else None)
        suspected = "summary generation"
    else:
        return _default_analysis(replay_result, facts)

    return _result(
        facts=facts,
        stages=stages,
        reproduced_original_failure=reproduced,
        chain_status=chain_status,
        suspected_segment=suspected,
        confirmed_facts=confirmed,
        excluded_scope=excluded,
    )


def _analyze_negative_cases(replay_result: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    target = replay_result.get("replay_target")
    if target == "test_create_duplicate_subscription":
        first_ok = facts.get("first_create_status") == 201
        second_ok = facts.get("second_create_status") == 409
        no_duplicate_rows = facts.get("subscription_business_key_count_after") == 1
        stages = [
            (MAIN_STATE_WRITE, first_ok),
            (REQUEST_VALIDATION, second_ok),
            (NEGATIVE_SIDE_EFFECT_ABSENCE, no_duplicate_rows),
        ]
        reproduced = bool(first_ok and (not second_ok or not no_duplicate_rows))
        chain_status = "interrupted" if not first_ok else "complete"
        confirmed = _filtered_texts(
            _status_fact(facts, "first_create_status", "第一次创建订阅"),
            _status_fact(facts, "second_create_status", "第二次重复创建"),
            f"重复创建后业务键对应记录数为 {facts.get('subscription_business_key_count_after')}" if facts.get("subscription_business_key_count_after") is not None else None,
        )
        excluded = _filtered_texts(
            "第一次创建订阅已成功" if first_ok else None,
            "重复创建的冲突状态码已按预期返回" if second_ok else None,
            "重复创建后未产生多余订阅记录" if no_duplicate_rows else None,
        )
        suspected = "duplicate subscription conflict handling"
    elif target == "test_create_subscription_with_unknown_dashboard":
        status_ok = facts.get("unknown_dashboard_status") == 404
        side_effect_ok = facts.get("subscription_business_key_count_after") in (0, None)
        stages = [(REQUEST_VALIDATION, status_ok), (NEGATIVE_SIDE_EFFECT_ABSENCE, side_effect_ok)]
        reproduced = bool((not status_ok) or (status_ok and not side_effect_ok))
        chain_status = "complete"
        confirmed = _filtered_texts(
            _status_fact(facts, "unknown_dashboard_status", "未知 dashboard 创建订阅"),
            "未知 dashboard 后数据库中未新增订阅记录" if side_effect_ok else "未知 dashboard 后数据库中仍出现订阅记录",
        )
        excluded = _filtered_texts(
            "未知 dashboard 的错误状态码已按预期返回" if status_ok else None,
            "错误分支后未观察到额外订阅记录" if side_effect_ok else None,
        )
        suspected = "negative request validation / no-side-effect guard"
    elif target == "test_create_subscription_with_illegal_channel":
        status_ok = facts.get("invalid_channel_status") == 422
        side_effect_ok = facts.get("subscription_business_key_count_after") in (0, None)
        stages = [(REQUEST_VALIDATION, status_ok), (NEGATIVE_SIDE_EFFECT_ABSENCE, side_effect_ok)]
        reproduced = bool((not status_ok) or (status_ok and not side_effect_ok))
        chain_status = "complete"
        confirmed = _filtered_texts(
            _status_fact(facts, "invalid_channel_status", "非法 channel 创建订阅"),
            "非法 channel 后数据库中未新增订阅记录" if side_effect_ok else "非法 channel 后数据库中仍出现订阅记录",
        )
        excluded = _filtered_texts(
            "非法 channel 的错误状态码已按预期返回" if status_ok else None,
            "错误分支后未观察到额外订阅记录" if side_effect_ok else None,
        )
        suspected = "negative request validation / no-side-effect guard"
    elif target == "test_get_unknown_share_token":
        status_ok = facts.get("unknown_share_status") == 404
        side_effect_ok = (facts.get("share_row_after_present") is False) and (facts.get("share_cache_exists_after") is False)
        stages = [(REQUEST_VALIDATION, status_ok), (NEGATIVE_SIDE_EFFECT_ABSENCE, side_effect_ok)]
        reproduced = bool((not status_ok) or (status_ok and not side_effect_ok))
        chain_status = "complete"
        confirmed = _filtered_texts(
            _status_fact(facts, "unknown_share_status", "读取未知分享 token"),
            "未知 token 后数据库和缓存都未产生副作用" if side_effect_ok else "未知 token 后仍观察到数据库或缓存副作用",
        )
        excluded = _filtered_texts(
            "未知 token 的错误状态码已按预期返回" if status_ok else None,
            "错误分支后未观察到数据库或缓存副作用" if side_effect_ok else None,
        )
        suspected = "negative request validation / no-side-effect guard"
    elif target == "test_get_expired_share_link":
        create_ok = facts.get("create_status") == 201
        expired_status_ok = facts.get("expired_share_status") == 410
        stages = [(MAIN_STATE_WRITE, create_ok), (REQUEST_VALIDATION, expired_status_ok)]
        reproduced = bool(create_ok and not expired_status_ok)
        chain_status = "interrupted" if not create_ok else "complete"
        confirmed = _filtered_texts(
            _status_fact(facts, "create_status", "创建过期分享链接"),
            _status_fact(facts, "expired_share_status", "读取过期分享链接"),
        )
        excluded = _filtered_texts(
            "创建过期分享链接步骤已成功" if create_ok else None,
            "过期分享链接返回 410" if expired_status_ok else None,
        )
        suspected = "expired share link negative branch"
    else:
        return _default_analysis(replay_result, facts)

    return _result(
        facts=facts,
        stages=stages,
        reproduced_original_failure=reproduced,
        chain_status=chain_status,
        suspected_segment=suspected,
        confirmed_facts=confirmed,
        excluded_scope=excluded,
    )


def _default_analysis(replay_result: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    stages: list[tuple[str, bool]] = []
    confirmed = []
    first_http_failure = False
    for step in replay_result.get("http_steps", []) or []:
        status_code = step.get("status_code")
        expected_status = step.get("expected_status")
        ok = _matches_expected(status_code, expected_status)
        stages.append((REQUEST_VALIDATION, ok))
        confirmed.append(f"{step.get('step')} 返回 {status_code}，预期 {expected_status}")
        if not ok:
            first_http_failure = True
            break
    return _result(
        facts=facts,
        stages=stages,
        reproduced_original_failure=False,
        chain_status="interrupted" if first_http_failure else "complete",
        suspected_segment="request validation" if first_http_failure else None,
        confirmed_facts=confirmed,
        excluded_scope=[],
    )


def analyze_replay_result(replay_result: dict[str, Any]) -> dict[str, Any]:
    facts = _extract_facts(replay_result)
    preflight = _preflight_failure(replay_result, facts)
    if preflight is not None:
        return preflight

    target = replay_result.get("replay_target")
    if target == "test_subscriptions_are_cached_and_invalidated":
        return _analyze_subscriptions_are_cached_and_invalidated(facts)
    if target == "test_share_link_is_cached_and_invalidated":
        return _analyze_share_link_is_cached_and_invalidated(facts)
    if target == "test_dashboard_summary_is_cached":
        return _analyze_dashboard_summary_is_cached(facts)
    if target == "test_subscription_written_to_mysql":
        return _analyze_subscription_written_to_mysql(facts)
    if target == "test_share_link_written_to_mysql_and_view_count_updated":
        return _analyze_share_link_written_to_mysql_and_view_count_updated(facts)
    if target == "test_get_subscriptions_success":
        return _analyze_get_subscriptions_success(facts)
    if target in {
        "test_create_subscription_success",
        "test_create_share_link_success",
        "test_get_share_link_success",
        "test_get_dashboard_summary_success",
    }:
        return _analyze_generic_success_case(replay_result, facts)
    if target in NEGATIVE_STYLE_TARGETS:
        return _analyze_negative_cases(replay_result, facts)
    return _default_analysis(replay_result, facts)
