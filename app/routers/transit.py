from fastapi import APIRouter, HTTPException, Query

from app.schemas.transit import (
    TransitLiveFeedResponse,
    TransitNearbyResponse,
    TransitProviderResponse,
    TransitRouteResponse,
)
from app.services.transit_service import TransitService

router = APIRouter(prefix="/api/v1/transit", tags=["transit"])


@router.get("/providers", response_model=list[TransitProviderResponse])
def list_transit_providers():
    return TransitService.list_providers()


@router.get("/route", response_model=TransitRouteResponse)
def get_transit_route(
    origin: str = Query(..., min_length=1),
    destination: str = Query(..., min_length=1),
    network: str = Query(default="rapid-rail-kl"),
):
    try:
        return TransitService.plan_route(origin=origin, destination=destination, network=network)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/live", response_model=TransitLiveFeedResponse)
def get_live_transit_feed(
    provider_key: str = Query(..., min_length=1, description="Provider key from /api/v1/transit/providers"),
):
    try:
        return TransitService.get_live_feed(provider_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/nearby", response_model=TransitNearbyResponse)
def get_nearby_transit(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    radius_meters: float = Query(default=1000, gt=0, le=10000),
    provider_key: str | None = Query(default=None),
    mode: str | None = Query(default="bus"),
    query: str | None = Query(default=None),
):
    try:
        return TransitService.get_nearby_live(
            latitude=latitude,
            longitude=longitude,
            radius_meters=radius_meters,
            provider_key=provider_key,
            mode=mode,
            query=query,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
