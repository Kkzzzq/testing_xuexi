from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from typing import Any

import requests
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import cache
from app.agent_log import record_event
from app.ai_client import AIClient, AIClientError
from app.config import (
    AI_API_KEY,
    AI_ENABLED,
    AI_MAX_PANEL_JSON_CHARS,
    AI_MAX_PANELS_TO_SUMMARIZE,
    AI_MODEL,
    AI_PROMPT_VERSION,
    AI_PROVIDER,
    CACHE_TTL_SECONDS,
    DASHBOARD_EXISTS_CACHE_TTL_SECONDS,
    GRAFANA_ADMIN_PASSWORD,
    GRAFANA_ADMIN_USER,
    GRAFANA_BASE_URL,
    demo_fault_enabled,
)
from app.metrics import (
    CACHE_HIT_COUNT,
    CACHE_INVALIDATION_COUNT,
    CACHE_MISS_COUNT,
    CACHE_OPERATION_LATENCY,
    DB_OPERATION_LATENCY,
    GRAFANA_REQUEST_COUNT,
    GRAFANA_REQUEST_FAILURE_COUNT,
    GRAFANA_REQUEST_LATENCY,
    SHARE_LINK_EXPIRED_COUNT,
    SUBSCRIPTION_CONFLICT_COUNT,
    SUMMARY_SOURCE_COUNT,
    observe_histogram,
)
from app.models import ShareLink, Subscription


_GRAFANA_DASHBOARD_TIMEOUT_SECONDS = 10


class DashboardLookupUnavailableError(RuntimeError):
    """Raised when Dashboard Hub cannot determine dashboard existence because Grafana is unavailable."""


def _cache_get_json(cache_name: str, key: str):
    with observe_histogram(CACHE_OPERATION_LATENCY, "get", cache_name):
        return cache.get_json(key)


def _cache_set_json(cache_name: str, key: str, value: dict | bool, ex: int | None = None):
    with observe_histogram(CACHE_OPERATION_LATENCY, "set", cache_name):
        cache.set_json(key, value, ex=ex)


def _cache_delete(cache_name: str, key: str, reason: str | None = None):
    with observe_histogram(CACHE_OPERATION_LATENCY, "delete", cache_name):
        cache.delete(key)
    if reason:
        CACHE_INVALIDATION_COUNT.labels(cache_name=cache_name, reason=reason).inc()


def _fetch_grafana_dashboard_response(dashboard_uid: str):
    endpoint = "dashboard_by_uid"
    with observe_histogram(GRAFANA_REQUEST_LATENCY, endpoint):
        try:
            response = requests.get(
                f"{GRAFANA_BASE_URL}/api/dashboards/uid/{dashboard_uid}",
                auth=(GRAFANA_ADMIN_USER, GRAFANA_ADMIN_PASSWORD),
                timeout=_GRAFANA_DASHBOARD_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            GRAFANA_REQUEST_COUNT.labels(endpoint=endpoint, status="exception").inc()
            GRAFANA_REQUEST_FAILURE_COUNT.labels(endpoint=endpoint, reason=exc.__class__.__name__).inc()
            raise

    GRAFANA_REQUEST_COUNT.labels(endpoint=endpoint, status=str(response.status_code)).inc()
    if response.status_code >= 400:
        GRAFANA_REQUEST_FAILURE_COUNT.labels(endpoint=endpoint, reason=f"http_{response.status_code}").inc()
    return response


def _dashboard_exists_cache_key(dashboard_uid: str) -> str:
    return f"dashhub:dashboard_exists:{dashboard_uid}"


def dashboard_exists(dashboard_uid: str) -> bool:
    cache_key = _dashboard_exists_cache_key(dashboard_uid)
    record_event("dashboard_lookup_started", dashboard_uid=dashboard_uid, cache_key=cache_key)

    cached = _cache_get_json("dashboard_exists", cache_key)
    if cached is not None:
        CACHE_HIT_COUNT.labels(cache_name="dashboard_exists").inc()
        exists = bool(cached)
        record_event(
            "dashboard_lookup_cache_hit",
            dashboard_uid=dashboard_uid,
            cache_key=cache_key,
            exists=exists,
        )
        return exists

    CACHE_MISS_COUNT.labels(cache_name="dashboard_exists").inc()
    record_event("dashboard_lookup_cache_miss", dashboard_uid=dashboard_uid, cache_key=cache_key)

    try:
        response = _fetch_grafana_dashboard_response(dashboard_uid)
    except requests.RequestException as exc:
        record_event(
            "dashboard_lookup_request_failed",
            dashboard_uid=dashboard_uid,
            error_class=exc.__class__.__name__,
            error=str(exc),
        )
        raise DashboardLookupUnavailableError("grafana dashboard lookup failed") from exc

    if response.status_code >= 500:
        record_event(
            "dashboard_lookup_upstream_failed",
            dashboard_uid=dashboard_uid,
            status_code=response.status_code,
        )
        raise DashboardLookupUnavailableError(
            f"grafana dashboard lookup returned status {response.status_code}"
        )

    exists = response.status_code == 200
    _cache_set_json(
        "dashboard_exists",
        cache_key,
        exists,
        ex=DASHBOARD_EXISTS_CACHE_TTL_SECONDS,
    )
    record_event(
        "dashboard_lookup_finished",
        dashboard_uid=dashboard_uid,
        cache_key=cache_key,
        status_code=response.status_code,
        exists=exists,
    )
    return exists


def _flatten_panels(panels: list[dict] | None) -> list[dict]:
    if not panels:
        return []

    result: list[dict] = []
    for panel in panels:
        result.append(panel)
        nested = panel.get("panels")
        if nested:
            result.extend(_flatten_panels(nested))
    return result


def _extract_panel_titles(panels: list[dict] | None) -> list[str]:
    flat_panels = _flatten_panels(panels)

    titles: list[str] = []
    seen: set[str] = set()
    for panel in flat_panels:
        title = panel.get("title")
        if title and title not in seen:
            seen.add(title)
            titles.append(title)
    return titles


def _serialize_panel_for_ai(panel: dict[str, Any]) -> str:
    panel_json = json.dumps(panel, ensure_ascii=False, separators=(",", ":"), default=str)
    return panel_json[:AI_MAX_PANEL_JSON_CHARS]


def _extract_panel_payloads(panels: list[dict] | None) -> list[dict[str, Any]]:
    flat_panels = _flatten_panels(panels)
    payloads: list[dict[str, Any]] = []

    for panel in flat_panels[:AI_MAX_PANELS_TO_SUMMARIZE]:
        payloads.append(
            {
                "title": panel.get("title", ""),
                "panel_json": _serialize_panel_for_ai(panel),
            }
        )

    return payloads


def fetch_dashboard_context(dashboard_uid: str) -> dict | None:
    record_event("summary_dashboard_context_fetch_started", dashboard_uid=dashboard_uid)
    try:
        response = _fetch_grafana_dashboard_response(dashboard_uid)
    except requests.RequestException as exc:
        record_event(
            "summary_dashboard_context_fetch_request_failed",
            dashboard_uid=dashboard_uid,
            error_class=exc.__class__.__name__,
            error=str(exc),
        )
        raise DashboardLookupUnavailableError("grafana summary lookup failed") from exc

    if response.status_code >= 500:
        record_event(
            "summary_dashboard_context_fetch_failed",
            dashboard_uid=dashboard_uid,
            status_code=response.status_code,
        )
        raise DashboardLookupUnavailableError(
            f"grafana summary lookup returned status {response.status_code}"
        )

    if response.status_code != 200:
        record_event(
            "summary_dashboard_context_fetch_failed",
            dashboard_uid=dashboard_uid,
            status_code=response.status_code,
        )
        return None

    try:
        payload = response.json()
    except ValueError as exc:
        record_event(
            "summary_dashboard_context_parse_failed",
            dashboard_uid=dashboard_uid,
            error_class=exc.__class__.__name__,
            error=str(exc),
        )
        raise DashboardLookupUnavailableError("grafana summary payload parse failed") from exc

    dashboard = payload.get("dashboard") or {}
    meta = payload.get("meta") or {}
    panels = _extract_panel_titles(dashboard.get("panels"))
    panel_payloads = _extract_panel_payloads(dashboard.get("panels"))
    tags = [str(tag) for tag in (dashboard.get("tags") or []) if tag is not None]

    context = {
        "dashboard_uid": dashboard_uid,
        "title": dashboard.get("title") or dashboard_uid,
        "url": meta.get("url") or f"/d/{dashboard_uid}",
        "tags": tags,
        "panels": panels,
        "panel_payloads": panel_payloads,
    }
    record_event(
        "summary_dashboard_context_fetch_finished",
        dashboard_uid=dashboard_uid,
        title=context["title"],
        panel_count=len(panels),
    )
    return context


def build_fallback_summary(title: str, panels: list[str]) -> str:
    panel_text = "、".join(panels[:3]) if panels else "暂无面板信息"
    if len(panels) > 3:
        panel_text += " 等"
    return f"Dashboard《{title}》当前包含 {len(panels)} 个面板，核心内容包括：{panel_text}。"


def _summary_cache_key(dashboard_uid: str) -> str:
    return f"dashhub:summary:{dashboard_uid}:{AI_PROVIDER}:{AI_MODEL}:{AI_PROMPT_VERSION}"



def _share_link_payload(row: ShareLink) -> dict[str, Any]:
    return {
        "dashboard_uid": row.dashboard_uid,
        "token": row.token,
        "expire_at": row.expire_at.isoformat() if row.expire_at else None,
        "view_count": row.view_count,
    }


def _parse_expire_at(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _is_expired(expire_at: datetime | None) -> bool:
    return expire_at is not None and expire_at <= datetime.now(timezone.utc)


def create_subscription(db: Session, dashboard_uid: str, user_login: str, channel: str, cron: str):
    record_event(
        "subscription_create_started",
        dashboard_uid=dashboard_uid,
        user_login=user_login,
        channel=channel,
        cron=cron,
    )
    subscription = Subscription(
        dashboard_uid=dashboard_uid,
        user_login=user_login,
        channel=channel,
        cron=cron,
    )
    db.add(subscription)
    try:
        with observe_histogram(DB_OPERATION_LATENCY, "subscription_create_commit"):
            db.commit()
    except IntegrityError:
        db.rollback()
        SUBSCRIPTION_CONFLICT_COUNT.labels(channel=channel).inc()
        record_event(
            "subscription_create_integrity_error",
            dashboard_uid=dashboard_uid,
            user_login=user_login,
            channel=channel,
        )
        raise

    with observe_histogram(DB_OPERATION_LATENCY, "subscription_create_refresh"):
        db.refresh(subscription)

    cache_key = f"dashhub:subscriptions:{dashboard_uid}"
    _cache_delete("subscriptions", cache_key, reason="subscription_create")
    record_event(
        "subscription_create_finished",
        dashboard_uid=dashboard_uid,
        user_login=user_login,
        channel=channel,
        subscription_id=subscription.id,
        cache_key=cache_key,
        cache_invalidated=True,
    )
    return subscription


def list_subscriptions(db: Session, dashboard_uid: str):
    cache_key = f"dashhub:subscriptions:{dashboard_uid}"
    record_event("subscription_list_started", dashboard_uid=dashboard_uid, cache_key=cache_key)
    cached = _cache_get_json("subscriptions", cache_key)
    if cached is not None:
        CACHE_HIT_COUNT.labels(cache_name="subscriptions").inc()
        record_event(
            "subscription_list_cache_hit",
            dashboard_uid=dashboard_uid,
            cache_key=cache_key,
            item_count=len(cached.get("items", [])),
        )
        return cached

    CACHE_MISS_COUNT.labels(cache_name="subscriptions").inc()
    record_event("subscription_list_cache_miss", dashboard_uid=dashboard_uid, cache_key=cache_key)

    with observe_histogram(DB_OPERATION_LATENCY, "subscription_list_query"):
        rows = (
            db.query(Subscription)
            .filter(Subscription.dashboard_uid == dashboard_uid)
            .order_by(Subscription.id.desc())
            .all()
        )

    payload = {
        "dashboard_uid": dashboard_uid,
        "items": [
            {
                "id": row.id,
                "dashboard_uid": row.dashboard_uid,
                "user_login": row.user_login,
                "channel": row.channel,
                "cron": row.cron,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
    }
    _cache_set_json("subscriptions", cache_key, payload, ex=CACHE_TTL_SECONDS)
    record_event(
        "subscription_list_cache_populated",
        dashboard_uid=dashboard_uid,
        cache_key=cache_key,
        item_count=len(payload["items"]),
    )
    return payload


def delete_subscription(db: Session, subscription_id: int):
    record_event("subscription_delete_started", subscription_id=subscription_id)
    with observe_histogram(DB_OPERATION_LATENCY, "subscription_delete_lookup"):
        row = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not row:
        record_event("subscription_delete_not_found", subscription_id=subscription_id)
        return None

    dashboard_uid = row.dashboard_uid
    cache_key = f"dashhub:subscriptions:{dashboard_uid}"
    db.delete(row)
    with observe_histogram(DB_OPERATION_LATENCY, "subscription_delete_commit"):
        db.commit()
    record_event(
        "subscription_delete_db_committed",
        subscription_id=subscription_id,
        dashboard_uid=dashboard_uid,
    )

    if not demo_fault_enabled("subscription_cache_bug"):
        _cache_delete("subscriptions", cache_key, reason="subscription_delete")
        record_event(
            "subscription_delete_cache_invalidated",
            subscription_id=subscription_id,
            dashboard_uid=dashboard_uid,
            cache_key=cache_key,
        )

    return row


def create_share_link(db: Session, dashboard_uid: str, expire_at: datetime | None):
    token = secrets.token_urlsafe(12)
    record_event(
        "share_link_create_started",
        dashboard_uid=dashboard_uid,
        token=token,
        expire_at=expire_at.isoformat() if expire_at else None,
    )
    share_link = ShareLink(
        dashboard_uid=dashboard_uid,
        token=token,
        expire_at=expire_at,
    )
    db.add(share_link)
    with observe_histogram(DB_OPERATION_LATENCY, "share_link_create_commit"):
        db.commit()
    with observe_histogram(DB_OPERATION_LATENCY, "share_link_create_refresh"):
        db.refresh(share_link)
    cache_key = f"dashhub:share:{token}"
    _cache_set_json("share_link", cache_key, _share_link_payload(share_link), ex=CACHE_TTL_SECONDS)
    record_event(
        "share_link_create_finished",
        dashboard_uid=dashboard_uid,
        token=token,
        cache_key=cache_key,
    )
    return share_link


def get_share_link(db: Session, token: str):
    cache_key = f"dashhub:share:{token}"
    record_event("share_link_read_started", token=token, cache_key=cache_key)
    cached = _cache_get_json("share_link", cache_key)
    if cached is not None:
        CACHE_HIT_COUNT.labels(cache_name="share_link").inc()
        record_event("share_link_cache_hit", token=token, cache_key=cache_key)
        expire_at = _parse_expire_at(cached.get("expire_at"))
        if _is_expired(expire_at):
            _cache_delete("share_link", cache_key)
            SHARE_LINK_EXPIRED_COUNT.labels(source="cache").inc()
            record_event("share_link_cache_entry_expired", token=token, cache_key=cache_key)
            return "expired"

        with observe_histogram(DB_OPERATION_LATENCY, "share_link_increment_after_cache_hit"):
            updated_rows = (
                db.query(ShareLink)
                .filter(ShareLink.token == token)
                .update({ShareLink.view_count: ShareLink.view_count + 1}, synchronize_session=False)
            )
            db.commit()
        if updated_rows == 0:
            _cache_delete("share_link", cache_key)
            record_event("share_link_db_row_missing_after_cache_hit", token=token, cache_key=cache_key)
            return None

        cached["view_count"] = int(cached.get("view_count", 0)) + 1
        _cache_set_json("share_link", cache_key, cached, ex=CACHE_TTL_SECONDS)
        record_event(
            "share_link_cache_refreshed_after_read",
            token=token,
            cache_key=cache_key,
            view_count=cached["view_count"],
        )
        return cached

    CACHE_MISS_COUNT.labels(cache_name="share_link").inc()
    record_event("share_link_cache_miss", token=token, cache_key=cache_key)

    with observe_histogram(DB_OPERATION_LATENCY, "share_link_read_lookup"):
        row = db.query(ShareLink).filter(ShareLink.token == token).first()
    if not row:
        _cache_delete("share_link", cache_key)
        record_event("share_link_not_found", token=token, cache_key=cache_key)
        return None
    if _is_expired(row.expire_at):
        _cache_delete("share_link", cache_key)
        SHARE_LINK_EXPIRED_COUNT.labels(source="db").inc()
        record_event("share_link_expired", token=token, cache_key=cache_key)
        return "expired"

    row.view_count += 1
    with observe_histogram(DB_OPERATION_LATENCY, "share_link_read_commit"):
        db.commit()
    with observe_histogram(DB_OPERATION_LATENCY, "share_link_read_refresh"):
        db.refresh(row)
    payload = _share_link_payload(row)
    _cache_set_json("share_link", cache_key, payload, ex=CACHE_TTL_SECONDS)
    record_event(
        "share_link_read_finished",
        token=token,
        cache_key=cache_key,
        view_count=row.view_count,
    )
    return payload


def delete_share_link(db: Session, token: str):
    record_event("share_link_delete_started", token=token)
    with observe_histogram(DB_OPERATION_LATENCY, "share_link_delete_lookup"):
        row = db.query(ShareLink).filter(ShareLink.token == token).first()
    if not row:
        record_event("share_link_delete_not_found", token=token)
        return None
    db.delete(row)
    with observe_histogram(DB_OPERATION_LATENCY, "share_link_delete_commit"):
        db.commit()
    cache_key = f"dashhub:share:{token}"
    if not demo_fault_enabled("share_link_cache_bug"):
        _cache_delete("share_link", cache_key, reason="share_link_delete")
        record_event("share_link_delete_cache_invalidated", token=token, cache_key=cache_key)
    record_event("share_link_delete_finished", token=token, cache_key=cache_key)
    return row


def get_dashboard_summary(dashboard_uid: str):
    cache_key = _summary_cache_key(dashboard_uid)
    record_event("summary_read_started", dashboard_uid=dashboard_uid, cache_key=cache_key)
    cached = _cache_get_json("summary", cache_key)
    if cached is not None:
        CACHE_HIT_COUNT.labels(cache_name="summary").inc()
        SUMMARY_SOURCE_COUNT.labels(source=cached.get("source", "fallback")).inc()
        record_event(
            "summary_cache_hit",
            dashboard_uid=dashboard_uid,
            cache_key=cache_key,
            source=cached.get("source", "fallback"),
        )
        return cached

    CACHE_MISS_COUNT.labels(cache_name="summary").inc()
    record_event("summary_cache_miss", dashboard_uid=dashboard_uid, cache_key=cache_key)

    context = fetch_dashboard_context(dashboard_uid)
    if not context:
        record_event("summary_dashboard_context_missing", dashboard_uid=dashboard_uid)
        return None

    payload = {
        "dashboard_uid": context["dashboard_uid"],
        "title": context["title"],
        "url": context["url"],
        "ai_summary": build_fallback_summary(context["title"], context["panels"]),
        "provider": AI_PROVIDER,
        "model": AI_MODEL,
        "prompt_version": AI_PROMPT_VERSION,
        "source": "fallback",
    }

    if AI_ENABLED and AI_API_KEY:
        client = AIClient()
        try:
            record_event(
                "summary_ai_request_started",
                dashboard_uid=dashboard_uid,
                provider=AI_PROVIDER,
                model=AI_MODEL,
            )
            ai_result = client.summarize_dashboard(
                title=context["title"],
                tags=context["tags"],
                panel_titles=context["panels"],
                panel_payloads=context["panel_payloads"],
            )
            if ai_result.get("ai_summary"):
                payload["ai_summary"] = ai_result["ai_summary"]
                payload["provider"] = ai_result.get("provider", payload["provider"])
                payload["model"] = ai_result.get("model", payload["model"])
                payload["prompt_version"] = ai_result.get("prompt_version", payload["prompt_version"])
                payload["source"] = "ai"
            record_event(
                "summary_ai_request_finished",
                dashboard_uid=dashboard_uid,
                provider=AI_PROVIDER,
                model=AI_MODEL,
                source=payload["source"],
            )
        except AIClientError as exc:
            record_event(
                "summary_ai_request_failed",
                dashboard_uid=dashboard_uid,
                provider=AI_PROVIDER,
                model=AI_MODEL,
                error_class=exc.__class__.__name__,
                error=str(exc),
            )

    SUMMARY_SOURCE_COUNT.labels(source=payload["source"]).inc()
    _cache_set_json("summary", cache_key, payload, ex=CACHE_TTL_SECONDS)
    record_event(
        "summary_cache_populated",
        dashboard_uid=dashboard_uid,
        cache_key=cache_key,
        source=payload["source"],
    )
    return payload
