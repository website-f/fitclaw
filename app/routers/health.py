from fastapi import APIRouter, Response, status

from app.schemas.health import HealthResponse
from app.services.health_service import HealthService

router = APIRouter(tags=["health"])


@router.get("/health/live", response_model=HealthResponse)
def liveness() -> HealthResponse:
    return HealthResponse(status="ok", services={"api": "up"}, detail={})


@router.get("/health/ready", response_model=HealthResponse)
def readiness(response: Response) -> HealthResponse:
    snapshot = HealthService.snapshot()
    if snapshot["status"] != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(**snapshot)


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(**HealthService.snapshot())

