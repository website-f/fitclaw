from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import math
import re
import time
from zoneinfo import ZoneInfo

import httpx

from app.core.config import get_settings
from app.schemas.weather import WeatherForecastResponse, WeatherWarningResponse
from app.services.command_result import CommandResult

settings = get_settings()


@dataclass(slots=True)
class ResolvedWeatherQuery:
    requested_location: str
    resolved_location: str
    requested_date: date
    date_label: str
    defaulted_location: bool = False


class WeatherService:
    OFFICIAL_FORECAST_URL = "https://api.data.gov.my/weather/forecast"
    OFFICIAL_WARNING_URL = "https://api.data.gov.my/weather/warning"
    OPEN_METEO_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
    OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
    WEATHER_PATTERN = re.compile(
        r"\b(weather|forecast|temperature|temp|rain|raining|thunderstorm|storm|humidity|wind|warning|alert|cuaca)\b",
        re.IGNORECASE,
    )
    WARNING_ONLY_PATTERN = re.compile(r"\b(?:warning|warnings|alert|alerts)\b", re.IGNORECASE)
    CURRENT_QUERY_PATTERN = re.compile(
        r"\b(?:current|currently|right now|now|at the moment|already raining|is it raining|going to rain|gonna rain|will it rain)\b",
        re.IGNORECASE,
    )
    RAIN_STATUS_PATTERN = re.compile(
        r"\b(?:is it(?: already)? raining|already raining|going to rain|will it rain|chance of rain|rain later|rain soon)\b",
        re.IGNORECASE,
    )
    LOCATION_CAPTURE_PATTERN = re.compile(
        r"\b(?:in|for|at|around|near)\s+([A-Za-z][A-Za-z0-9 .'-]{1,60}?)(?=(?:\s+\b(?:today|tomorrow|weekend|next|on|weather|forecast|rain|warning|please|now)\b)|[?.!,]|$)",
        re.IGNORECASE,
    )
    STRIP_LOCATION_PREFIX = re.compile(
        r"\b(?:weather|forecast|temperature|temp|rain|raining|thunderstorm|storm|humidity|wind|warning|alert|cuaca|will it|is it|what(?:'s| is)|show|give me|tell me|can you tell me|could you tell me|the|current|right now|now)\b",
        re.IGNORECASE,
    )
    _client = httpx.Client(timeout=20, follow_redirects=True)
    _forecast_cache: dict[str, object] = {"expires_at": 0.0, "data": []}
    _warning_cache: dict[str, object] = {"expires_at": 0.0, "data": []}
    _geocode_cache: dict[str, tuple[float, dict[str, object]]] = {}

    @staticmethod
    def try_handle(text: str) -> CommandResult | None:
        normalized = text.strip()
        if not normalized or not WeatherService.WEATHER_PATTERN.search(normalized):
            return None

        try:
            if WeatherService.WARNING_ONLY_PATTERN.search(normalized) and not re.search(
                r"\b(?:forecast|temperature|temp|rain|raining|humidity|wind)\b",
                normalized,
                re.IGNORECASE,
            ):
                return WeatherService._handle_warning_query(normalized)

            forecast = WeatherService.resolve_query(normalized)
        except Exception as exc:
            return CommandResult(
                reply=(
                    "I couldn't reach the weather service cleanly right now.\n\n"
                    f"{exc}\n\n"
                    "This weather feature does not require an API key, so a rebuild or transient upstream issue is the more likely cause."
                ),
                provider="weather-error",
            )
        lines = [
            (
                f"Current weather in {forecast.resolved_location}:"
                if forecast.is_current_conditions
                else f"Weather for {forecast.resolved_location} on {forecast.date_label}:"
            ),
            f"- Summary: {forecast.summary}",
        ]
        if forecast.rain_status_summary:
            lines.append(f"- Rain status: {forecast.rain_status_summary}")
        if forecast.current_temp_c is not None:
            lines.append(f"- Current temperature: {WeatherService._fmt_temp(forecast.current_temp_c)}")
        if forecast.current_apparent_temp_c is not None:
            lines.append(f"- Feels like: {WeatherService._fmt_temp(forecast.current_apparent_temp_c)}")
        if forecast.current_humidity_pct is not None:
            lines.append(f"- Humidity: {round(forecast.current_humidity_pct)}%")
        if forecast.current_wind_speed_kph is not None:
            lines.append(f"- Current wind: {round(forecast.current_wind_speed_kph)} km/h")
        if forecast.morning_forecast:
            lines.append(f"- Morning: {forecast.morning_forecast}")
        if forecast.afternoon_forecast:
            lines.append(f"- Afternoon: {forecast.afternoon_forecast}")
        if forecast.night_forecast:
            lines.append(f"- Night: {forecast.night_forecast}")
        if forecast.min_temp_c is not None or forecast.max_temp_c is not None:
            lines.append(
                f"- Temperature: {WeatherService._fmt_temp(forecast.min_temp_c)} to {WeatherService._fmt_temp(forecast.max_temp_c)}"
            )
        if forecast.precipitation_probability_max is not None:
            lines.append(f"- Precipitation chance: {round(forecast.precipitation_probability_max)}%")
        if forecast.wind_speed_max_kph is not None:
            lines.append(f"- Max wind: {round(forecast.wind_speed_max_kph)} km/h")
        if forecast.warnings:
            lines.append("")
            lines.append("Active warnings:")
            for warning in forecast.warnings[:3]:
                until = warning.valid_to.strftime("%Y-%m-%d %I:%M %p") if warning.valid_to else "unspecified"
                lines.append(f"- {warning.title} until {until}: {warning.text}")
        else:
            lines.append("- Active warnings: none matched for this area")

        return CommandResult(reply="\n".join(lines), provider=f"weather:{forecast.source}")

    @staticmethod
    def _handle_warning_query(text: str) -> CommandResult:
        location = None
        match = WeatherService.LOCATION_CAPTURE_PATTERN.search(text)
        if match:
            location = match.group(1).strip(" .,-")
        warnings = WeatherService.get_warnings(location)
        if not warnings:
            detail = f" for {location}" if location else ""
            return CommandResult(
                reply=f"I did not find any active official weather warnings{detail} right now.",
                provider="weather:official-malaysia",
            )

        lines = ["Active official weather warnings:"]
        for item in warnings[:5]:
            until = item.valid_to.strftime("%Y-%m-%d %I:%M %p") if item.valid_to else "unspecified"
            lines.append(f"- {item.title} until {until}: {item.text}")
        return CommandResult(reply="\n".join(lines), provider="weather:official-malaysia")

    @staticmethod
    def resolve_query(text: str) -> WeatherForecastResponse:
        query = WeatherService._resolve_query(text)
        if WeatherService.CURRENT_QUERY_PATTERN.search(text) or WeatherService.RAIN_STATUS_PATTERN.search(text):
            return WeatherService._fetch_open_meteo_current(query)
        official = WeatherService._try_official_forecast(query)
        if official is not None:
            return official
        return WeatherService._fetch_open_meteo_forecast(query)

    @staticmethod
    def get_warnings(location: str | None = None) -> list[WeatherWarningResponse]:
        warnings = WeatherService._fetch_official_warnings()
        if not location:
            return warnings
        return WeatherService._filter_warnings_by_location(warnings, location)

    @staticmethod
    def _resolve_query(text: str) -> ResolvedWeatherQuery:
        normalized_text = re.sub(r"\s+", " ", text).strip()
        normalized_text = re.sub(r"[?.!,]+$", "", normalized_text).strip()
        today = datetime.now(ZoneInfo(settings.timezone)).date()
        requested_date, date_label = WeatherService._parse_date_reference(normalized_text, today)
        official_names = WeatherService._official_location_names()
        location = WeatherService._match_location_from_catalog(normalized_text, official_names)
        defaulted = False
        if not location:
            match = WeatherService.LOCATION_CAPTURE_PATTERN.search(normalized_text)
            if match:
                location = match.group(1).strip(" .,-")
        if not location:
            simple_in_match = re.search(r"\bin\s+([A-Za-z][A-Za-z0-9 .'-]{1,60})$", normalized_text, re.IGNORECASE)
            if simple_in_match:
                location = simple_in_match.group(1).strip(" .,-")
        if not location:
            cleaned = WeatherService.STRIP_LOCATION_PREFIX.sub(" ", normalized_text)
            cleaned = re.sub(
                r"\b(today|tomorrow|weekend|next|on|will|be|like|in malaysia|going|already|or|is|it|to|rain|raining|soon|later|please)\b",
                " ",
                cleaned,
                flags=re.IGNORECASE,
            )
            cleaned = " ".join(cleaned.split()).strip(" .,-")
            if cleaned and len(cleaned) > 2 and WeatherService._looks_like_location_candidate(cleaned):
                location = cleaned
        if not location:
            location = settings.weather_default_location
            defaulted = True
        return ResolvedWeatherQuery(
            requested_location=location,
            resolved_location=location,
            requested_date=requested_date,
            date_label=date_label,
            defaulted_location=defaulted,
        )

    @staticmethod
    def _try_official_forecast(query: ResolvedWeatherQuery) -> WeatherForecastResponse | None:
        forecast_rows = WeatherService._fetch_official_forecast_rows()
        if not forecast_rows:
            return None

        location_name = WeatherService._resolve_official_location(query.requested_location, forecast_rows)
        if not location_name:
            return None

        matching = [
            row
            for row in forecast_rows
            if str((row.get("location") or {}).get("location_name", "")).strip().lower() == location_name.lower()
        ]
        if not matching:
            return None

        selected_row = None
        for row in matching:
            if row.get("date") == query.requested_date.isoformat():
                selected_row = row
                break

        if selected_row is None:
            dated_rows = sorted(
                matching,
                key=lambda item: abs((WeatherService._parse_iso_date(str(item.get("date"))) - query.requested_date).days),
            )
            selected_row = dated_rows[0]

        requested_date = WeatherService._parse_iso_date(str(selected_row.get("date")))
        warnings = WeatherService._filter_warnings_by_location(WeatherService._fetch_official_warnings(), location_name)
        summary_bm = str(selected_row.get("summary_forecast") or "").strip()
        summary_when = str(selected_row.get("summary_when") or "").strip()
        translated = WeatherService._translate_bm_summary(summary_bm)
        summary = summary_bm if not translated else f"{summary_bm} ({translated})"
        if summary_when:
            summary = f"{summary} - {summary_when}"

        return WeatherForecastResponse(
            source="official-malaysia",
            location=query.requested_location,
            resolved_location=location_name,
            requested_date=requested_date,
            date_label=WeatherService._format_date_label(requested_date),
            summary=summary,
            morning_forecast=WeatherService._annotate_bm(str(selected_row.get("morning_forecast") or "").strip()),
            afternoon_forecast=WeatherService._annotate_bm(str(selected_row.get("afternoon_forecast") or "").strip()),
            night_forecast=WeatherService._annotate_bm(str(selected_row.get("night_forecast") or "").strip()),
            min_temp_c=WeatherService._safe_float(selected_row.get("min_temp")),
            max_temp_c=WeatherService._safe_float(selected_row.get("max_temp")),
            warnings=warnings,
        )

    @staticmethod
    def _fetch_open_meteo_forecast(query: ResolvedWeatherQuery) -> WeatherForecastResponse:
        geo = WeatherService._geocode(query.requested_location)
        if geo is None:
            raise ValueError(f"I could not resolve a weather location from `{query.requested_location}`.")

        params = {
            "latitude": geo["latitude"],
            "longitude": geo["longitude"],
            "timezone": geo.get("timezone") or settings.timezone,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max",
            "forecast_days": 7,
        }
        response = WeatherService._client.get(WeatherService.OPEN_METEO_FORECAST_URL, params=params)
        response.raise_for_status()
        data = response.json()

        dates = [WeatherService._parse_iso_date(item) for item in data.get("daily", {}).get("time", [])]
        if not dates:
            raise ValueError("Open-Meteo did not return any daily forecast data.")

        index = 0
        if query.requested_date in dates:
            index = dates.index(query.requested_date)
        else:
            index = min(range(len(dates)), key=lambda idx: abs((dates[idx] - query.requested_date).days))

        requested_date = dates[index]
        daily = data.get("daily", {})
        summary = WeatherService._open_meteo_summary(
            WeatherService._safe_int((daily.get("weather_code") or [None])[index]),
            WeatherService._safe_float((daily.get("precipitation_probability_max") or [None])[index]),
        )

        return WeatherForecastResponse(
            source="open-meteo",
            location=query.requested_location,
            resolved_location=str(geo.get("name") or query.requested_location),
            requested_date=requested_date,
            date_label=WeatherService._format_date_label(requested_date),
            summary=summary,
            current_temp_c=WeatherService._safe_float((data.get("current") or {}).get("temperature_2m")),
            current_apparent_temp_c=WeatherService._safe_float((data.get("current") or {}).get("apparent_temperature")),
            current_humidity_pct=WeatherService._safe_float((data.get("current") or {}).get("relative_humidity_2m")),
            current_wind_speed_kph=WeatherService._safe_float((data.get("current") or {}).get("wind_speed_10m")),
            min_temp_c=WeatherService._safe_float((daily.get("temperature_2m_min") or [None])[index]),
            max_temp_c=WeatherService._safe_float((daily.get("temperature_2m_max") or [None])[index]),
            precipitation_probability_max=WeatherService._safe_float((daily.get("precipitation_probability_max") or [None])[index]),
            wind_speed_max_kph=WeatherService._safe_float((daily.get("wind_speed_10m_max") or [None])[index]),
            warnings=[],
        )

    @staticmethod
    def _fetch_open_meteo_current(query: ResolvedWeatherQuery) -> WeatherForecastResponse:
        geo = WeatherService._geocode(query.requested_location)
        if geo is None:
            raise ValueError(f"I could not resolve a weather location from `{query.requested_location}`.")

        params = {
            "latitude": geo["latitude"],
            "longitude": geo["longitude"],
            "timezone": geo.get("timezone") or settings.timezone,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,precipitation,rain,showers",
            "hourly": "weather_code,precipitation_probability,precipitation,rain,showers",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "forecast_days": 1,
            "forecast_hours": 12,
        }
        response = WeatherService._client.get(WeatherService.OPEN_METEO_FORECAST_URL, params=params)
        response.raise_for_status()
        data = response.json()
        current = data.get("current") or {}
        daily = data.get("daily") or {}
        hourly = data.get("hourly") or {}
        current_code = WeatherService._safe_int(current.get("weather_code"))
        current_precip = WeatherService._safe_float((daily.get("precipitation_probability_max") or [None])[0])
        summary = WeatherService._open_meteo_summary(current_code, current_precip)
        rain_status_summary = WeatherService._build_rain_status_summary(
            current_code=current_code,
            current_precipitation=WeatherService._safe_float(current.get("precipitation")),
            current_rain=WeatherService._safe_float(current.get("rain")),
            current_showers=WeatherService._safe_float(current.get("showers")),
            hourly_precipitation_probabilities=hourly.get("precipitation_probability") or [],
            hourly_precipitation=hourly.get("precipitation") or [],
            hourly_rain=hourly.get("rain") or [],
            hourly_showers=hourly.get("showers") or [],
            hourly_weather_codes=hourly.get("weather_code") or [],
        )

        warnings = WeatherService._filter_warnings_by_location(
            WeatherService._fetch_official_warnings(),
            str(geo.get("name") or query.requested_location),
        )
        today = datetime.now(ZoneInfo(settings.timezone)).date()
        return WeatherForecastResponse(
            source="open-meteo",
            location=query.requested_location,
            resolved_location=str(geo.get("name") or query.requested_location),
            requested_date=today,
            date_label=WeatherService._format_date_label(today),
            summary=summary,
            is_current_conditions=True,
            rain_status_summary=rain_status_summary,
            current_temp_c=WeatherService._safe_float(current.get("temperature_2m")),
            current_apparent_temp_c=WeatherService._safe_float(current.get("apparent_temperature")),
            current_humidity_pct=WeatherService._safe_float(current.get("relative_humidity_2m")),
            current_wind_speed_kph=WeatherService._safe_float(current.get("wind_speed_10m")),
            min_temp_c=WeatherService._safe_float((daily.get("temperature_2m_min") or [None])[0]),
            max_temp_c=WeatherService._safe_float((daily.get("temperature_2m_max") or [None])[0]),
            precipitation_probability_max=current_precip,
            warnings=warnings,
        )

    @staticmethod
    def _fetch_official_forecast_rows() -> list[dict[str, object]]:
        now = time.monotonic()
        if float(WeatherService._forecast_cache.get("expires_at", 0.0)) > now:
            cached = WeatherService._forecast_cache.get("data", [])
            return list(cached) if isinstance(cached, list) else []

        response = WeatherService._client.get(WeatherService.OFFICIAL_FORECAST_URL)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("Unexpected Malaysia weather forecast response format.")
        WeatherService._forecast_cache = {"expires_at": now + float(settings.weather_cache_ttl_seconds), "data": payload}
        return payload

    @staticmethod
    def _fetch_official_warnings() -> list[WeatherWarningResponse]:
        now = time.monotonic()
        if float(WeatherService._warning_cache.get("expires_at", 0.0)) > now:
            cached = WeatherService._warning_cache.get("data", [])
            return list(cached) if isinstance(cached, list) else []

        response = WeatherService._client.get(WeatherService.OFFICIAL_WARNING_URL)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("Unexpected Malaysia weather warning response format.")

        warnings: list[WeatherWarningResponse] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            issue = item.get("warning_issue") or {}
            text = str(item.get("text_en") or item.get("text_bm") or "").strip()
            warnings.append(
                WeatherWarningResponse(
                    title=str(issue.get("title_en") or issue.get("title_bm") or "Weather warning").strip(),
                    valid_from=WeatherService._parse_iso_datetime(item.get("valid_from")),
                    valid_to=WeatherService._parse_iso_datetime(item.get("valid_to")),
                    text=text,
                    source="official-malaysia",
                )
            )

        WeatherService._warning_cache = {"expires_at": now + min(float(settings.weather_cache_ttl_seconds), 300.0), "data": warnings}
        return warnings

    @staticmethod
    def _official_location_names() -> list[str]:
        names = {
            str((row.get("location") or {}).get("location_name", "")).strip()
            for row in WeatherService._fetch_official_forecast_rows()
        }
        return sorted(name for name in names if name)

    @staticmethod
    def _resolve_official_location(query: str, rows: list[dict[str, object]]) -> str | None:
        names = {
            str((row.get("location") or {}).get("location_name", "")).strip()
            for row in rows
            if (row.get("location") or {}).get("location_name")
        }
        if not names:
            return None
        return WeatherService._best_location_match(query, list(names))

    @staticmethod
    def _match_location_from_catalog(text: str, names: list[str]) -> str | None:
        normalized_text = WeatherService._normalize_location_name(text)
        matches = [
            name
            for name in names
            if WeatherService._normalize_location_name(name) and WeatherService._normalize_location_name(name) in normalized_text
        ]
        if not matches:
            return None
        matches.sort(key=lambda item: (-len(WeatherService._normalize_location_name(item)), item))
        return matches[0]

    @staticmethod
    def _best_location_match(query: str, names: list[str]) -> str | None:
        qnorm = WeatherService._normalize_location_name(query)
        if not qnorm:
            return None

        exact = [name for name in names if WeatherService._normalize_location_name(name) == qnorm]
        if exact:
            return exact[0]

        contains = [name for name in names if qnorm in WeatherService._normalize_location_name(name)]
        if contains:
            contains.sort(key=lambda item: (len(WeatherService._normalize_location_name(item)), item))
            return contains[0]
        return None

    @staticmethod
    def _filter_warnings_by_location(
        warnings: list[WeatherWarningResponse],
        location: str,
    ) -> list[WeatherWarningResponse]:
        if not location:
            return warnings
        location_tokens = [
            token
            for token in re.split(r"[^a-z0-9]+", WeatherService._normalize_location_name(location))
            if token and len(token) > 2
        ]
        if not location_tokens:
            return warnings

        results = []
        for item in warnings:
            haystack = WeatherService._normalize_location_name(f"{item.title} {item.text}")
            if any(token in haystack for token in location_tokens):
                results.append(item)
        return results

    @staticmethod
    def _geocode(location: str) -> dict[str, object] | None:
        key = WeatherService._normalize_location_name(location)
        cached = WeatherService._geocode_cache.get(key)
        now = time.monotonic()
        if cached and cached[0] > now:
            return cached[1]

        response = WeatherService._client.get(
            WeatherService.OPEN_METEO_GEOCODE_URL,
            params={"name": location, "count": 5, "language": "en", "format": "json"},
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results") or []
        if not results:
            return None

        preferred = next((item for item in results if str(item.get("country_code", "")).upper() == "MY"), results[0])
        WeatherService._geocode_cache[key] = (now + 21600.0, preferred)
        return preferred

    @staticmethod
    def _parse_date_reference(text: str, today: date) -> tuple[date, str]:
        lowered = text.lower()
        if "day after tomorrow" in lowered:
            target = today + timedelta(days=2)
            return target, WeatherService._format_date_label(target)
        if "tomorrow" in lowered:
            target = today + timedelta(days=1)
            return target, WeatherService._format_date_label(target)
        if "today" in lowered or "tonight" in lowered:
            return today, WeatherService._format_date_label(today)

        iso_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", lowered)
        if iso_match:
            target = WeatherService._parse_iso_date(iso_match.group(1))
            return target, WeatherService._format_date_label(target)

        weekday_names = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }
        for name, weekday in weekday_names.items():
            if re.search(rf"\bnext\s+{name}\b", lowered):
                delta = (weekday - today.weekday()) % 7 or 7
                target = today + timedelta(days=delta)
                return target, WeatherService._format_date_label(target)
            if re.search(rf"\b(?:this|on)\s+{name}\b", lowered):
                delta = (weekday - today.weekday()) % 7
                target = today + timedelta(days=delta)
                return target, WeatherService._format_date_label(target)

        return today, WeatherService._format_date_label(today)

    @staticmethod
    def _format_date_label(value: date) -> str:
        return value.strftime("%A, %B %d, %Y")

    @staticmethod
    def _translate_bm_summary(value: str) -> str:
        translations = {
            "tiada hujan": "no rain",
            "hujan di satu dua tempat": "rain in one or two places",
            "ribut petir di satu dua tempat": "thunderstorms in one or two places",
            "hujan di beberapa tempat": "rain in several places",
            "ribut petir di beberapa tempat": "thunderstorms in several places",
            "hujan di kebanyakan tempat": "rain in most places",
            "ribut petir di kebanyakan tempat": "thunderstorms in most places",
        }
        lowered = value.lower().strip()
        return translations.get(lowered, "")

    @staticmethod
    def _annotate_bm(value: str) -> str | None:
        if not value:
            return None
        translated = WeatherService._translate_bm_summary(value)
        return value if not translated else f"{value} ({translated})"

    @staticmethod
    def _open_meteo_summary(weather_code: int | None, precipitation: float | None) -> str:
        labels = {
            0: "Clear sky",
            1: "Mainly clear",
            2: "Partly cloudy",
            3: "Overcast",
            45: "Fog",
            48: "Depositing rime fog",
            51: "Light drizzle",
            53: "Moderate drizzle",
            55: "Dense drizzle",
            61: "Slight rain",
            63: "Moderate rain",
            65: "Heavy rain",
            71: "Slight snow",
            80: "Rain showers",
            81: "Moderate rain showers",
            82: "Violent rain showers",
            95: "Thunderstorm",
            96: "Thunderstorm with hail",
            99: "Severe thunderstorm with hail",
        }
        label = labels.get(weather_code or 0, "Forecast available")
        if precipitation is None:
            return label
        return f"{label} with about {round(precipitation)}% precipitation probability"

    @staticmethod
    def _build_rain_status_summary(
        current_code: int | None,
        current_precipitation: float | None,
        current_rain: float | None,
        current_showers: float | None,
        hourly_precipitation_probabilities: list[object],
        hourly_precipitation: list[object],
        hourly_rain: list[object],
        hourly_showers: list[object],
        hourly_weather_codes: list[object],
    ) -> str:
        is_raining_now = WeatherService._is_raining_now(
            current_code=current_code,
            current_precipitation=current_precipitation,
            current_rain=current_rain,
            current_showers=current_showers,
        )
        if is_raining_now:
            return "Yes, it is raining right now."

        next_rain_hour = WeatherService._first_rainy_hour_index(
            hourly_precipitation_probabilities=hourly_precipitation_probabilities,
            hourly_precipitation=hourly_precipitation,
            hourly_rain=hourly_rain,
            hourly_showers=hourly_showers,
            hourly_weather_codes=hourly_weather_codes,
        )
        if next_rain_hour == 0:
            return "Rain looks imminent within the next hour."
        if next_rain_hour is not None:
            hours = next_rain_hour + 1
            return f"It is not raining right now, but rain looks likely within about {hours} hour{'s' if hours != 1 else ''}."
        return "It is not raining right now, and there is no strong rain signal in the next several hours."

    @staticmethod
    def _is_raining_now(
        current_code: int | None,
        current_precipitation: float | None,
        current_rain: float | None,
        current_showers: float | None,
    ) -> bool:
        if WeatherService._is_rain_code(current_code):
            return True
        for value in (current_precipitation, current_rain, current_showers):
            if value is not None and value > 0.05:
                return True
        return False

    @staticmethod
    def _first_rainy_hour_index(
        hourly_precipitation_probabilities: list[object],
        hourly_precipitation: list[object],
        hourly_rain: list[object],
        hourly_showers: list[object],
        hourly_weather_codes: list[object],
    ) -> int | None:
        horizon = min(
            6,
            max(
                len(hourly_precipitation_probabilities),
                len(hourly_precipitation),
                len(hourly_rain),
                len(hourly_showers),
                len(hourly_weather_codes),
            ),
        )
        for index in range(horizon):
            probability = WeatherService._safe_float(hourly_precipitation_probabilities[index]) if index < len(hourly_precipitation_probabilities) else None
            precipitation = WeatherService._safe_float(hourly_precipitation[index]) if index < len(hourly_precipitation) else None
            rain = WeatherService._safe_float(hourly_rain[index]) if index < len(hourly_rain) else None
            showers = WeatherService._safe_float(hourly_showers[index]) if index < len(hourly_showers) else None
            weather_code = WeatherService._safe_int(hourly_weather_codes[index]) if index < len(hourly_weather_codes) else None
            if WeatherService._is_rain_code(weather_code):
                return index
            if precipitation is not None and precipitation > 0.1:
                return index
            if rain is not None and rain > 0.05:
                return index
            if showers is not None and showers > 0.05:
                return index
            if probability is not None and probability >= 55:
                return index
        return None

    @staticmethod
    def _is_rain_code(code: int | None) -> bool:
        if code is None:
            return False
        return code in {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}

    @staticmethod
    def _looks_like_location_candidate(value: str) -> bool:
        tokens = [token for token in re.split(r"[^a-z0-9]+", value.lower()) if token]
        if not tokens:
            return False
        blocked = {
            "going",
            "already",
            "raining",
            "rain",
            "weather",
            "forecast",
            "or",
            "to",
            "is",
            "it",
            "will",
            "soon",
            "later",
            "current",
            "currently",
            "now",
            "right",
            "moment",
            "please",
            "tell",
            "me",
        }
        meaningful = [token for token in tokens if token not in blocked]
        return bool(meaningful)

    @staticmethod
    def _fmt_temp(value: float | None) -> str:
        if value is None or math.isnan(value):
            return "--"
        return f"{round(value)} C"

    @staticmethod
    def _normalize_location_name(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", value.lower())

    @staticmethod
    def _parse_iso_date(value: str) -> date:
        return datetime.strptime(value, "%Y-%m-%d").date()

    @staticmethod
    def _parse_iso_datetime(value: object) -> datetime | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    @staticmethod
    def _safe_float(value: object) -> float | None:
        if value in {None, ""}:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_int(value: object) -> int | None:
        if value in {None, ""}:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
