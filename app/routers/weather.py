from fastapi import APIRouter, HTTPException, Query

from app.schemas.weather import WeatherForecastResponse, WeatherWarningResponse
from app.services.weather_service import WeatherService

router = APIRouter(prefix="/api/v1/weather", tags=["weather"])


@router.get("/forecast", response_model=WeatherForecastResponse)
def get_weather_forecast(
    query: str = Query(..., min_length=1, description="Natural language weather query, for example 'weather in Shah Alam tomorrow'"),
):
    try:
        return WeatherService.resolve_query(query)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/warnings", response_model=list[WeatherWarningResponse])
def get_weather_warnings(
    location: str | None = Query(default=None, description="Optional location filter"),
):
    return WeatherService.get_warnings(location)
