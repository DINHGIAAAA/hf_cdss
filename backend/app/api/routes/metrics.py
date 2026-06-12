from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.core.metrics import render_prometheus


router = APIRouter()


@router.get("/metrics", response_class=PlainTextResponse)
def metrics() -> PlainTextResponse:
    return PlainTextResponse(render_prometheus(), media_type="text/plain; version=0.0.4")
