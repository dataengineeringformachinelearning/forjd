from fastapi import APIRouter

from app.api.v1 import anomaly, ingest, pulse, sessions, stack, tenants

api_router = APIRouter()
api_router.include_router(pulse.router)
api_router.include_router(stack.router)
api_router.include_router(anomaly.router)
api_router.include_router(tenants.router)
api_router.include_router(ingest.router)
api_router.include_router(sessions.router)
