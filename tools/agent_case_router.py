from __future__ import annotations

from tools.agent_allure_reader import AllureCase


EXACT_SCENARIO_BY_TEST_NAME: dict[str, str] = {
    "test_create_subscription_success": "subscription_persistence",
    "test_subscription_written_to_mysql": "subscription_persistence",
    "test_create_duplicate_subscription": "subscription_conflict",
    "test_get_subscriptions_success": "subscription_cache_invalidation",
    "test_subscriptions_are_cached_and_invalidated": "subscription_cache_invalidation",
    "test_create_share_link_success": "share_link_view_count",
    "test_get_share_link_success": "share_link_view_count",
    "test_share_link_written_to_mysql_and_view_count_updated": "share_link_view_count",
    "test_share_link_is_cached_and_invalidated": "share_link_cache_invalidation",
    "test_get_dashboard_summary_success": "summary_cache",
    "test_dashboard_summary_is_cached": "summary_cache",
    "test_get_expired_share_link": "expired_share_link",
    "test_create_subscription_with_unknown_dashboard": "subscription_unknown_dashboard",
    "test_get_unknown_share_token": "unknown_share_token",
    "test_create_subscription_with_illegal_channel": "illegal_subscription_channel",
}


def route_case(case: AllureCase) -> tuple[str | None, str]:
    if case.fault_scenario:
        return case.fault_scenario, "allure_label"

    candidate_names = [case.name, case.short_test_name]
    for candidate in candidate_names:
        if candidate in EXACT_SCENARIO_BY_TEST_NAME:
            return EXACT_SCENARIO_BY_TEST_NAME[candidate], "exact_name"

    haystack = " ".join([case.name, case.full_name, case.message]).lower()

    if "duplicate" in haystack or "conflict" in haystack:
        return "subscription_conflict", "keyword"
    if "illegal_channel" in haystack or ("channel" in haystack and "422" in haystack):
        return "illegal_subscription_channel", "keyword"
    if "expired" in haystack and "share" in haystack:
        return "expired_share_link", "keyword"
    if "summary" in haystack:
        return "summary_cache", "keyword"
    if "share" in haystack and "cache" in haystack:
        return "share_link_cache_invalidation", "keyword"
    if "share" in haystack and "token" in haystack and "404" in haystack:
        return "unknown_share_token", "keyword"
    if "subscription" in haystack and "cache" in haystack:
        return "subscription_cache_invalidation", "keyword"
    if "subscription" in haystack and "mysql" in haystack:
        return "subscription_persistence", "keyword"
    if "share" in haystack and "mysql" in haystack:
        return "share_link_view_count", "keyword"
    if "unknown_dashboard" in haystack or ("dashboard" in haystack and "404" in haystack):
        return "subscription_unknown_dashboard", "keyword"

    return None, "unmatched"
