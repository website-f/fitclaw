from datetime import datetime

from pydantic import BaseModel, Field


class TransitProviderResponse(BaseModel):
    key: str
    label: str
    mode: str
    agency: str
    category: str | None = None
    live_supported: bool = True
    notes: str | None = None


class TransitRouteStepResponse(BaseModel):
    step_type: str
    instruction: str
    from_stop: str
    to_stop: str
    route_id: str | None = None
    route_label: str | None = None
    stop_count: int = 0
    estimated_minutes: float = 0.0


class TransitRouteResponse(BaseModel):
    source: str
    network: str
    origin_query: str
    destination_query: str
    matched_origin: str
    matched_destination: str
    total_estimated_minutes: float
    steps: list[TransitRouteStepResponse] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class TransitLiveVehicleResponse(BaseModel):
    vehicle_id: str | None = None
    trip_id: str | None = None
    route_id: str | None = None
    route_label: str | None = None
    license_plate: str | None = None
    latitude: float
    longitude: float
    bearing: float | None = None
    speed_kph: float | None = None
    timestamp: datetime | None = None


class TransitLiveFeedResponse(BaseModel):
    source: str
    provider_key: str
    label: str
    vehicle_count: int
    feed_timestamp: datetime | None = None
    vehicles: list[TransitLiveVehicleResponse] = Field(default_factory=list)


class TransitNearbyRouteResponse(BaseModel):
    provider_key: str
    provider_label: str
    mode: str
    route_id: str | None = None
    route_label: str
    vehicle_count: int = 0
    nearest_distance_meters: float | None = None


class TransitNearbyVehicleResponse(TransitLiveVehicleResponse):
    provider_key: str
    provider_label: str
    mode: str
    distance_meters: float


class TransitNearbyResponse(BaseModel):
    source: str
    latitude: float
    longitude: float
    radius_meters: float
    providers_scanned: list[str] = Field(default_factory=list)
    route_count: int = 0
    vehicle_count: int = 0
    routes: list[TransitNearbyRouteResponse] = Field(default_factory=list)
    vehicles: list[TransitNearbyVehicleResponse] = Field(default_factory=list)
