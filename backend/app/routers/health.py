"""Health endpoints.

Two distinct probes on purpose:
  /healthz  -- liveness: is the process alive? never touches the DB, so a DB
               blip cannot cause a pod restart storm.
  /readyz   -- readiness: can we actually serve traffic (DB reachable)?

The AI release gate reads /readyz plus the Prometheus metrics exposed at
/metrics, so these contracts are part of the platform's interface.
"""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.schemas import HealthOut

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthOut)
async def liveness() -> HealthOut:
    s = get_settings()
    return HealthOut(
        status="ok",
        environment=s.environment,
        cloud=s.cloud,
        version=s.release_version,
        database="not-checked",
    )


@router.get("/readyz", response_model=HealthOut)
async def readiness(
    response: Response, session: AsyncSession = Depends(get_session)
) -> HealthOut:
    s = get_settings()
    try:
        # Query the application table, not `SELECT 1`. A connectivity check
        # passes against an un-migrated database, which lets a pod that failed
        # to migrate report itself ready and start serving 500s. Touching the
        # real table means readiness implies "this pod can serve requests", so
        # a bad migration fails the rollout instead of reaching users.
        await session.execute(text("SELECT 1 FROM ideas LIMIT 1"))
        db_state = "ok"
    except Exception as exc:  # noqa: BLE001 - surfaced to the probe, not swallowed
        db_state = f"error: {type(exc).__name__}"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthOut(
        status="ok" if db_state == "ok" else "degraded",
        environment=s.environment,
        cloud=s.cloud,
        version=s.release_version,
        database=db_state,
    )
