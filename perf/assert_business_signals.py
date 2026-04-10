from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sum_values(mapping: dict[str, int] | None) -> int:
    if not isinstance(mapping, dict):
        return 0
    return sum(int(value) for value in mapping.values())


def _get_nested(payload: dict[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _delta(before: dict[str, Any], after: dict[str, Any], *keys: str) -> int:
    before_value = _get_nested(before, *keys)
    after_value = _get_nested(after, *keys)
    if isinstance(before_value, dict) or isinstance(after_value, dict):
        return _sum_values(after_value) - _sum_values(before_value)
    return int(after_value or 0) - int(before_value or 0)


def _metric_delta(before: dict[str, Any], after: dict[str, Any], section: str, bucket: str, key: str) -> int:
    return _delta(before, after, section, bucket, key)


def _http_status_delta(before: dict[str, Any], after: dict[str, Any], path: str, status: str) -> int:
    return _metric_delta(before, after, 'http', 'requests_by_path_status', f'{path}|{status}')


def _profile_assertions(before: dict[str, Any], after: dict[str, Any], profile: str) -> tuple[dict[str, int], list[str]]:
    summary: dict[str, int] = {}
    errors: list[str] = []

    if profile == 'write_conflict':
        conflicts_delta = _delta(before, after, 'business', 'subscription_conflicts_by_channel')
        invalidations_delta = _metric_delta(
            before,
            after,
            'cache',
            'invalidations_by_name_reason',
            'subscriptions|subscription_create',
        )
        status_201_delta = _http_status_delta(before, after, '/api/v1/subscriptions', '201')
        status_409_delta = _http_status_delta(before, after, '/api/v1/subscriptions', '409')
        summary['subscription_conflicts_delta'] = conflicts_delta
        summary['subscriptions_cache_invalidations_delta'] = invalidations_delta
        summary['subscription_http_201_delta'] = status_201_delta
        summary['subscription_http_409_delta'] = status_409_delta
        if conflicts_delta <= 0:
            errors.append('write_conflict 场景没有观察到 subscription_conflicts 指标增长，说明并发冲突没有真正打出来')
        if invalidations_delta <= 0:
            errors.append('write_conflict 场景没有观察到 subscriptions 缓存失效增长，说明正常写链路没有形成写后删缓存')
        if status_201_delta <= 0:
            errors.append('write_conflict 场景没有观察到 /api/v1/subscriptions 返回 201，说明正常写入流量没有形成对照组')
        if status_409_delta <= 0:
            errors.append('write_conflict 场景没有观察到 /api/v1/subscriptions 返回 409，说明固定冲突键没有形成有效竞争')
    elif profile == 'hot_read':
        subscription_hits_delta = _metric_delta(before, after, 'cache', 'hits_by_name', 'subscriptions')
        share_hits_delta = _metric_delta(before, after, 'cache', 'hits_by_name', 'share_link')
        status_200_sub_delta = _http_status_delta(before, after, '/api/v1/dashboards/{dashboard_uid}/subscriptions', '200')
        status_200_share_delta = _http_status_delta(before, after, '/api/v1/share-links/{token}', '200')
        summary['subscriptions_cache_hits_delta'] = subscription_hits_delta
        summary['share_link_cache_hits_delta'] = share_hits_delta
        summary['subscriptions_http_200_delta'] = status_200_sub_delta
        summary['share_link_http_200_delta'] = status_200_share_delta
        if subscription_hits_delta + share_hits_delta <= 0:
            errors.append('hot_read 场景没有观察到 subscriptions/share_link 缓存命中增长，说明热点读没有真正打到缓存')
        if status_200_sub_delta + status_200_share_delta <= 0:
            errors.append('hot_read 场景没有观察到核心读接口 200 增长，说明热点读流量没有真正命中业务接口')
    elif profile == 'cache_penetration':
        share_misses_delta = _metric_delta(before, after, 'cache', 'misses_by_name', 'share_link')
        dashboard_exists_misses_delta = _metric_delta(before, after, 'cache', 'misses_by_name', 'dashboard_exists')
        grafana_lookup_404_delta = _metric_delta(
            before,
            after,
            'grafana_outbound',
            'requests_by_endpoint_status',
            'dashboard_by_uid|404',
        )
        status_404_sub_delta = _http_status_delta(before, after, '/api/v1/dashboards/{dashboard_uid}/subscriptions', '404')
        status_404_share_delta = _http_status_delta(before, after, '/api/v1/share-links/{token}', '404')
        summary['share_link_cache_misses_delta'] = share_misses_delta
        summary['dashboard_exists_cache_misses_delta'] = dashboard_exists_misses_delta
        summary['grafana_dashboard_lookup_404_delta'] = grafana_lookup_404_delta
        summary['subscriptions_http_404_delta'] = status_404_sub_delta
        summary['share_link_http_404_delta'] = status_404_share_delta
        if share_misses_delta <= 0:
            errors.append('cache_penetration 场景没有观察到 share_link 缓存未命中增长，说明不存在 token 请求没有真正打到后端')
        if dashboard_exists_misses_delta <= 0:
            errors.append('cache_penetration 场景没有观察到 dashboard_exists 缓存未命中增长，说明不存在 dashboard 请求没有真正触发回源判断')
        if grafana_lookup_404_delta <= 0:
            errors.append('cache_penetration 场景没有观察到 dashboard_by_uid 404 回源增长，说明不存在 dashboard 请求没有真正打到上游 Grafana')
        if status_404_sub_delta + status_404_share_delta <= 0:
            errors.append('cache_penetration 场景没有观察到核心接口 404 增长，说明穿透流量没有形成稳定的业务返回')
    elif profile == 'cache_breakdown':
        subscription_misses_delta = _metric_delta(before, after, 'cache', 'misses_by_name', 'subscriptions')
        subscription_hits_delta = _metric_delta(before, after, 'cache', 'hits_by_name', 'subscriptions')
        status_200_delta = _http_status_delta(before, after, '/api/v1/dashboards/{dashboard_uid}/subscriptions', '200')
        summary['subscriptions_cache_misses_delta'] = subscription_misses_delta
        summary['subscriptions_cache_hits_delta'] = subscription_hits_delta
        summary['subscriptions_http_200_delta'] = status_200_delta
        if subscription_misses_delta <= 0:
            errors.append('cache_breakdown 场景没有观察到 subscriptions 缓存未命中增长，说明热点 key 删除后没有真正发生回源')
        if subscription_hits_delta <= 0:
            errors.append('cache_breakdown 场景没有观察到 subscriptions 缓存命中增长，说明热点 key 回填后没有持续形成热点读')
        if status_200_delta <= 0:
            errors.append('cache_breakdown 场景没有观察到订阅列表 200 增长，说明核心读流量没有真正打到业务接口')
    elif profile == 'cache_avalanche':
        subscription_misses_delta = _metric_delta(before, after, 'cache', 'misses_by_name', 'subscriptions')
        share_misses_delta = _metric_delta(before, after, 'cache', 'misses_by_name', 'share_link')
        dashboard_exists_misses_delta = _metric_delta(before, after, 'cache', 'misses_by_name', 'dashboard_exists')
        grafana_lookup_200_delta = _metric_delta(
            before,
            after,
            'grafana_outbound',
            'requests_by_endpoint_status',
            'dashboard_by_uid|200',
        )
        status_200_sub_delta = _http_status_delta(before, after, '/api/v1/dashboards/{dashboard_uid}/subscriptions', '200')
        status_200_share_delta = _http_status_delta(before, after, '/api/v1/share-links/{token}', '200')
        summary['subscriptions_cache_misses_delta'] = subscription_misses_delta
        summary['share_link_cache_misses_delta'] = share_misses_delta
        summary['dashboard_exists_cache_misses_delta'] = dashboard_exists_misses_delta
        summary['grafana_dashboard_lookup_200_delta'] = grafana_lookup_200_delta
        summary['subscriptions_http_200_delta'] = status_200_sub_delta
        summary['share_link_http_200_delta'] = status_200_share_delta
        if subscription_misses_delta <= 0:
            errors.append('cache_avalanche 场景没有观察到 subscriptions 缓存未命中增长，说明批量失效后没有形成订阅列表回源')
        if share_misses_delta <= 0:
            errors.append('cache_avalanche 场景没有观察到 share_link 缓存未命中增长，说明分享链接热点没有参与雪崩')
        if dashboard_exists_misses_delta <= 0:
            errors.append('cache_avalanche 场景没有观察到 dashboard_exists 缓存未命中增长，说明有效 dashboard 的存在性缓存没有参与批量过期')
        if grafana_lookup_200_delta <= 0:
            errors.append('cache_avalanche 场景没有观察到 dashboard_by_uid 200 回源增长，说明有效热点 dashboard 没有把压力打到上游 Grafana')
        if status_200_sub_delta + status_200_share_delta <= 0:
            errors.append('cache_avalanche 场景没有观察到核心读接口 200 增长，说明雪崩波次没有真正打到业务接口')
    else:
        errors.append(f'unsupported profile: {profile}')

    total_requests_delta = _delta(before, after, 'http', 'total_requests')
    summary['http_total_requests_delta'] = total_requests_delta
    if total_requests_delta <= 0:
        errors.append('没有观察到 HTTP 总请求数增长，说明压测流量本身没有真正进入服务')

    return summary, errors


def main() -> int:
    parser = argparse.ArgumentParser(description='Assert business-level signals from before/after metrics snapshots')
    parser.add_argument('--before', required=True)
    parser.add_argument('--after', required=True)
    parser.add_argument(
        '--profile',
        choices=['hot_read', 'write_conflict', 'cache_penetration', 'cache_breakdown', 'cache_avalanche'],
        required=True,
    )
    parser.add_argument('--summary-output')
    args = parser.parse_args()

    before = _load(args.before)
    after = _load(args.after)
    summary, errors = _profile_assertions(before, after, args.profile)

    payload = {
        'profile': args.profile,
        'summary': summary,
        'errors': errors,
    }

    if args.summary_output:
        Path(args.summary_output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit('Business signal assertion failed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
