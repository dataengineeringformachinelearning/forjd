from fastapi import APIRouter

from app.api.v1 import anomaly, pulse, stack

api_router = APIRouter()
api_router.include_router(pulse.router)
api_router.include_router(stack.router)
api_router.include_router(anomaly.router)
