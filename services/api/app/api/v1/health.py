"""Liveness and readiness probes.

Separate endpoints on purpose: an orchestrator restarts a container that fails
`live`, but only pulls it out of the load balancer when `ready` fails. Making
`live` depend on Postgres would restart every API container during a brief
database blip and turn a small outage into a large one.
"""

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app import __version__
from app.api.deps import DbSession
from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import get_redis

log = get_logger(__name__)
router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", summary="Process is running")
async def live() -> dict[str, str]:
    return {"status": "ok", "version": __version__, "environment": settings.ENVIRONMENT}


@router.get("/ready", summary="Dependencies are reachable")
async def ready(db: DbSession, response: Response) -> dict[str, object]:
    checks: dict[str, str] = {}

    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        log.error("health.database_unreachable", error=str(exc))
        checks["database"] = "unreachable"

    try:
        await get_redis().ping()
        checks["redis"] = "ok"
    except Exception as exc:
        log.error("health.redis_unreachable", error=str(exc))
        checks["redis"] = "unreachable"

    healthy = all(v == "ok" for v in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if healthy else "degraded", "checks": checks}
