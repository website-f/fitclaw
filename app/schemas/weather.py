from datetime import date, datetime

from pydantic import BaseModel, Field


class WeatherWarningResponse(BaseModel):
    title: str
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    text: str
    source: str = "official-malaysia"


class WeatherForecastResponse(BaseModel):
    source: str
    location: str
    resolved_location: str
    requested_date: date
    date_label: str
    summary: str
    is_current_conditions: bool = False
    rain_status_summary: str | None = None
    morning_forecast: str | None = None
    afternoon_forecast: str | None = None
    night_forecast: str | None = None
    min_temp_c: float | None = None
    max_temp_c: float | None = None
    current_temp_c: float | None = None
    current_apparent_temp_c: float | None = None
    current_humidity_pct: float | None = None
    current_wind_speed_kph: float | None = None
    precipitation_probability_max: float | None = None
    wind_speed_max_kph: float | None = None
    warnings: list[WeatherWarningResponse] = Field(default_factory=list)
