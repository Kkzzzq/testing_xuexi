from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crud import (
    create_share_link,
    create_subscription,
    dashboard_exists,
    delete_subscription,
    get_dashboard_summary,
    get_share_link,
    list_subscriptions,
)
from app.database import get_db
from app.metrics import REQUEST_COUNT, REQUEST_LATENCY, metrics_response
from app.schemas import DashboardSummaryOut, ShareLinkCreate, ShareLinkOut, SubscriptionCreate, SubscriptionOut, SubscriptionsListOut


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.init_db import main as init_db
    init_db()
    yield


app = FastAPI(title="Dashboard Hub", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def prometheus_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    path = request.url.path
    REQUEST_COUNT.labels(request.method, path, response.status_code).inc()
    REQUEST_LATENCY.labels(request.method, path).observe(elapsed)
    return response


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return metrics_response()


@app.post("/api/v1/subscriptions", response_model=SubscriptionOut, status_code=status.HTTP_201_CREATED)
def create_subscription_api(payload: SubscriptionCreate, db: Session = Depends(get_db)):
    if not dashboard_exists(payload.dashboard_uid):
        raise HTTPException(status_code=404, detail="dashboard not found")
    try:
        row = create_subscription(db, payload.dashboard_uid, payload.user_login, payload.channel, payload.cron)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="subscription already exists") from None
    return row


@app.get("/api/v1/dashboards/{dashboard_uid}/subscriptions", response_model=SubscriptionsListOut)
def list_subscriptions_api(dashboard_uid: str, db: Session = Depends(get_db)):
    if not dashboard_exists(dashboard_uid):
        raise HTTPException(status_code=404, detail="dashboard not found")
    return list_subscriptions(db, dashboard_uid)


@app.delete("/api/v1/subscriptions/{subscription_id}")
def delete_subscription_api(subscription_id: int, db: Session = Depends(get_db)):
    row = delete_subscription(db, subscription_id)
    if not row:
        raise HTTPException(status_code=404, detail="subscription not found")
    return {"status": "deleted", "id": subscription_id}


@app.post("/api/v1/share-links", response_model=ShareLinkOut, status_code=status.HTTP_201_CREATED)
def create_share_link_api(payload: ShareLinkCreate, db: Session = Depends(get_db)):
    if not dashboard_exists(payload.dashboard_uid):
        raise HTTPException(status_code=404, detail="dashboard not found")
    return create_share_link(db, payload.dashboard_uid, payload.expire_at)


@app.get("/api/v1/share-links/{token}", response_model=ShareLinkOut)
def get_share_link_api(token: str, db: Session = Depends(get_db)):
    payload = get_share_link(db, token)
    if payload is None:
        raise HTTPException(status_code=404, detail="share link not found")
    if payload == "expired":
        raise HTTPException(status_code=410, detail="share link expired")
    return payload


@app.get("/api/v1/dashboards/{dashboard_uid}/summary", response_model=DashboardSummaryOut)
def get_dashboard_summary_api(dashboard_uid: str):
    payload = get_dashboard_summary(dashboard_uid)
    if not payload:
        raise HTTPException(status_code=404, detail="dashboard not found")
    return payload
