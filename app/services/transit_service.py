from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
import csv
import io
import math
import re
import time
import zipfile
from heapq import heappop, heappush

import httpx

from app.core.config import get_settings
from app.schemas.transit import (
    TransitLiveFeedResponse,
    TransitLiveVehicleResponse,
    TransitNearbyResponse,
    TransitNearbyRouteResponse,
    TransitNearbyVehicleResponse,
    TransitProviderResponse,
    TransitRouteResponse,
    TransitRouteStepResponse,
)
from app.services.command_result import CommandResult

settings = get_settings()


@dataclass(slots=True)
class TransitProvider:
    key: str
    label: str
    mode: str
    agency: str
    category: str | None = None
    static_category: str | None = None
    live_supported: bool = True
    notes: str | None = None

    def to_response(self) -> TransitProviderResponse:
        return TransitProviderResponse(
            key=self.key,
            label=self.label,
            mode=self.mode,
            agency=self.agency,
            category=self.category,
            live_supported=self.live_supported,
            notes=self.notes,
        )


@dataclass(slots=True)
class TransitEdge:
    to_stop_id: str
    minutes: float
    edge_type: str
    route_id: str | None = None
    route_label: str | None = None
    from_stop_name: str | None = None
    to_stop_name: str | None = None


@dataclass(slots=True)
class TransitGraph:
    network: str
    source: str
    stops_by_id: dict[str, dict[str, str]]
    routes_by_id: dict[str, dict[str, str]]
    adjacency: dict[str, list[TransitEdge]]
    station_groups: dict[str, list[str]]


class TransitService:
    STATIC_BASE_URL = "https://api.data.gov.my/gtfs-static"
    REALTIME_BASE_URL = "https://api.data.gov.my/gtfs-realtime/vehicle-position"
    ROUTE_QUERY_PATTERN = re.compile(
        r"\b(?:route|public transport|transit|lrt|mrt|monorail|ktm|train|bus|commute|directions?)\b",
        re.IGNORECASE,
    )
    TRAVEL_INTENT_PATTERN = re.compile(
        r"\b(?:how\s+to\s+get|how\s+do\s+i\s+get|how\s+can\s+i\s+get|get\s+to|go\s+to|reach|travel|commute|best\s+way|fast(?:er|est)|quick(?:er|est))\b",
        re.IGNORECASE,
    )
    LIVE_QUERY_PATTERN = re.compile(
        r"\b(?:live|current|now|track)\b.*\b(?:bus|train|vehicle|transport|lrt|mrt|ktm)\b|"
        r"\b(?:bus|train|vehicle)\b.*\b(?:live|location|positions?)\b",
        re.IGNORECASE,
    )
    FROM_TO_PATTERN = re.compile(
        r"\bfrom\s+(.+?)\s+\bto\b\s+(.+?)(?=\s+\b(?:by|via|using|on)\b|[?.!,]|$)",
        re.IGNORECASE,
    )
    TO_FROM_PATTERN = re.compile(
        r"\bto\s+(.+?)\s+\bfrom\b\s+(.+?)(?=\s+\b(?:by|via|using|on)\b|[?.!,]|$)",
        re.IGNORECASE,
    )
    BETWEEN_PATTERN = re.compile(
        r"\bbetween\s+(.+?)\s+\band\b\s+(.+?)(?=\s+\b(?:by|via|using|on)\b|[?.!,]|$)",
        re.IGNORECASE,
    )
    _client = httpx.Client(timeout=30, follow_redirects=True)
    _graph_cache: dict[str, tuple[float, TransitGraph]] = {}
    _live_cache: dict[str, tuple[float, TransitLiveFeedResponse]] = {}
    _route_label_cache: dict[str, tuple[float, dict[str, str]]] = {}
    PROVIDERS: tuple[TransitProvider, ...] = (
        TransitProvider(
            key="rapid-rail-kl",
            label="Rapid Rail KL planner",
            mode="rail",
            agency="prasarana",
            static_category="rapid-rail-kl",
            live_supported=False,
            notes="Official static rail feed for LRT, MRT, and monorail route planning in Klang Valley.",
        ),
        TransitProvider(
            key="ktmb",
            label="KTMB live positions",
            mode="rail",
            agency="ktmb",
            static_category="ktmb",
            notes="Official KTMB live vehicle positions.",
        ),
        TransitProvider(
            key="prasarana:rapid-bus-kl",
            label="Rapid Bus KL live",
            mode="bus",
            agency="prasarana",
            category="rapid-bus-kl",
            static_category="rapid-bus-kl",
            notes="Official Rapid Bus KL live vehicle positions, updated about every 30 seconds.",
        ),
        TransitProvider(
            key="prasarana:rapid-bus-mrtfeeder",
            label="Rapid Bus MRT Feeder live",
            mode="bus",
            agency="prasarana",
            category="rapid-bus-mrtfeeder",
            static_category="rapid-bus-mrtfeeder",
            notes="Official MRT feeder bus live vehicle positions.",
        ),
        TransitProvider(
            key="prasarana:rapid-bus-penang",
            label="Rapid Bus Penang live",
            mode="bus",
            agency="prasarana",
            category="rapid-bus-penang",
            static_category="rapid-bus-penang",
            notes="Official Rapid Bus Penang live positions. Some trip and route ids may be imperfect in the feed.",
        ),
        TransitProvider(
            key="prasarana:rapid-bus-kuantan",
            label="Rapid Bus Kuantan live",
            mode="bus",
            agency="prasarana",
            category="rapid-bus-kuantan",
            static_category="rapid-bus-kuantan",
            notes="Official Rapid Bus Kuantan live positions. Some trip and route ids may be imperfect in the feed.",
        ),
        TransitProvider(key="mybas-kangar", label="BAS.MY Kangar live", mode="bus", agency="mybas", category="mybas-kangar"),
        TransitProvider(key="mybas-alor-setar", label="BAS.MY Alor Setar live", mode="bus", agency="mybas", category="mybas-alor-setar"),
        TransitProvider(key="mybas-kota-bharu", label="BAS.MY Kota Bharu live", mode="bus", agency="mybas", category="mybas-kota-bharu"),
        TransitProvider(key="mybas-kuala-terengganu", label="BAS.MY Kuala Terengganu live", mode="bus", agency="mybas", category="mybas-kuala-terengganu"),
        TransitProvider(key="mybas-ipoh", label="BAS.MY Ipoh live", mode="bus", agency="mybas", category="mybas-ipoh"),
        TransitProvider(key="mybas-seremban-a", label="BAS.MY Seremban A live", mode="bus", agency="mybas", category="mybas-seremban-a"),
        TransitProvider(key="mybas-seremban-b", label="BAS.MY Seremban B live", mode="bus", agency="mybas", category="mybas-seremban-b"),
        TransitProvider(key="mybas-melaka", label="BAS.MY Melaka live", mode="bus", agency="mybas", category="mybas-melaka"),
        TransitProvider(key="mybas-johor", label="BAS.MY Johor Bahru live", mode="bus", agency="mybas", category="mybas-johor"),
        TransitProvider(key="mybas-kuching", label="BAS.MY Kuching live", mode="bus", agency="mybas", category="mybas-kuching"),
    )
    PROVIDER_INDEX = {item.key: item for item in PROVIDERS}

    @staticmethod
    def try_handle(text: str) -> CommandResult | None:
        normalized = text.strip()
        if not normalized:
            return None

        has_route_keywords = bool(TransitService.ROUTE_QUERY_PATTERN.search(normalized))
        has_travel_intent = bool(TransitService.TRAVEL_INTENT_PATTERN.search(normalized))
        origin, destination = TransitService._extract_origin_destination(normalized)
        if not has_route_keywords and not (has_travel_intent and origin and destination):
            return None

        try:
            if TransitService.LIVE_QUERY_PATTERN.search(normalized):
                provider = TransitService._provider_from_text(normalized)
                if provider and not provider.live_supported:
                    return CommandResult(
                        reply=(
                            f"{provider.label} does not currently have a stable official live vehicle feed. "
                            "Use `/transit-live` for bus and KTMB live feeds, and use normal chat route planning for Rapid Rail KL."
                        ),
                        provider="transit-live",
                    )
                if provider:
                    feed = TransitService.get_live_feed(provider.key)
                    lines = [
                        f"Live feed for {feed.label}:",
                        f"- Vehicles in latest feed: {feed.vehicle_count}",
                    ]
                    if feed.feed_timestamp:
                        lines.append(f"- Feed timestamp: {feed.feed_timestamp.astimezone(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}")
                    for item in feed.vehicles[:8]:
                        route_label = item.route_label or item.route_id or item.trip_id or "live route"
                        vehicle_label = item.license_plate or item.vehicle_id or "vehicle"
                        lines.append(
                            f"- {vehicle_label} on {route_label} near {item.latitude:.5f}, {item.longitude:.5f}"
                        )
                    lines.append("")
                    lines.append("Open /transit-live in the web UI for the map view and provider selector.")
                    return CommandResult(reply="\n".join(lines), provider="transit-live")

            if not origin or not destination:
                return None

            network = TransitService._network_from_text(normalized)
            route = TransitService.plan_route(origin, destination, network=network)
            lines = [
                f"Best route on {route.network} from {route.matched_origin} to {route.matched_destination}:",
                f"- Estimated travel time: {round(route.total_estimated_minutes)} minutes",
            ]
            for step in route.steps:
                lines.append(f"- {step.instruction}")
            if route.notes:
                lines.append("")
                lines.extend(f"Note: {note}" for note in route.notes)
            return CommandResult(reply="\n".join(lines), provider="transit-route")
        except Exception as exc:
            return CommandResult(
                reply=(
                    "I couldn't complete that public transport lookup cleanly right now.\n\n"
                    f"{exc}\n\n"
                    "Try using clear origin and destination names, or open `/transit-live` for the live map and route tools."
                ),
                provider="transit-error",
            )

    @staticmethod
    def list_providers() -> list[TransitProviderResponse]:
        return [item.to_response() for item in TransitService.PROVIDERS]

    @staticmethod
    def plan_route(origin: str, destination: str, network: str = "rapid-rail-kl") -> TransitRouteResponse:
        graph = TransitService._load_graph(network)
        origin_candidates = TransitService._match_stations(origin, graph)
        destination_candidates = TransitService._match_stations(destination, graph)

        if not origin_candidates:
            raise ValueError(f"I could not match the origin `{origin}` to a station on {network}.")
        if not destination_candidates:
            raise ValueError(f"I could not match the destination `{destination}` to a station on {network}.")

        best = None
        for origin_name in origin_candidates[:3]:
            for destination_name in destination_candidates[:3]:
                for origin_stop in graph.station_groups[origin_name]:
                    for destination_stop in graph.station_groups[destination_name]:
                        path = TransitService._shortest_path(graph, origin_stop, destination_stop)
                        if path is None:
                            continue
                        if best is None or path[0] < best[0]:
                            best = (path[0], origin_name, destination_name, path[1])

        if best is None:
            raise ValueError(
                f"I could not find a connected public transport path from `{origin}` to `{destination}` on {network}."
            )

        total_minutes, matched_origin, matched_destination, edges = best
        steps = TransitService._build_route_steps(edges)
        notes = [
            "Route guidance is based on the official Malaysia GTFS static feed and may not reflect short-notice disruptions.",
        ]
        if network == "rapid-rail-kl":
            notes.append("Rapid Rail KL live train positions are not yet published as a stable official realtime feed.")
        return TransitRouteResponse(
            source=graph.source,
            network=network,
            origin_query=origin,
            destination_query=destination,
            matched_origin=matched_origin,
            matched_destination=matched_destination,
            total_estimated_minutes=round(total_minutes, 1),
            steps=steps,
            notes=notes,
        )

    @staticmethod
    def get_live_feed(provider_key: str) -> TransitLiveFeedResponse:
        provider = TransitService.PROVIDER_INDEX.get(provider_key)
        if provider is None:
            raise ValueError(f"Unknown transit provider `{provider_key}`.")
        if not provider.live_supported:
            raise ValueError(f"{provider.label} does not currently expose a stable official realtime feed.")

        now = time.monotonic()
        cached = TransitService._live_cache.get(provider.key)
        if cached and cached[0] > now:
            return cached[1]

        url = TransitService._build_live_url(provider)
        response = TransitService._client.get(url)
        response.raise_for_status()

        try:
            from google.transit import gtfs_realtime_pb2
        except Exception as exc:
            raise ValueError(
                "GTFS realtime parsing is not available yet. Install `gtfs-realtime-bindings` in the app image."
            ) from exc

        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(response.content)

        route_labels = TransitService._route_label_lookup_for_provider(provider)
        vehicles: list[TransitLiveVehicleResponse] = []
        feed_timestamp = datetime.fromtimestamp(feed.header.timestamp, UTC) if getattr(feed.header, "timestamp", 0) else None

        for entity in feed.entity:
            if not entity.HasField("vehicle"):
                continue
            vehicle = entity.vehicle
            if not vehicle.HasField("position"):
                continue

            route_id = vehicle.trip.route_id if vehicle.HasField("trip") else None
            trip_id = vehicle.trip.trip_id if vehicle.HasField("trip") else None
            route_label = (
                route_labels.get(route_id or "")
                or route_labels.get(f"trip:{trip_id or ''}")
                or route_id
                or trip_id
                or None
            )
            timestamp = datetime.fromtimestamp(vehicle.timestamp, UTC) if getattr(vehicle, "timestamp", 0) else feed_timestamp
            speed_kph = float(vehicle.position.speed) * 3.6 if getattr(vehicle.position, "speed", None) else None

            vehicles.append(
                TransitLiveVehicleResponse(
                    vehicle_id=vehicle.vehicle.id or None if vehicle.HasField("vehicle") else None,
                    trip_id=trip_id or None,
                    route_id=route_id or None,
                    route_label=route_label,
                    license_plate=vehicle.vehicle.license_plate or None if vehicle.HasField("vehicle") else None,
                    latitude=float(vehicle.position.latitude),
                    longitude=float(vehicle.position.longitude),
                    bearing=float(vehicle.position.bearing) if getattr(vehicle.position, "bearing", None) else None,
                    speed_kph=round(speed_kph, 1) if speed_kph is not None else None,
                    timestamp=timestamp,
                )
            )

        vehicles.sort(key=lambda item: (item.route_label or "", item.license_plate or item.vehicle_id or ""))
        result = TransitLiveFeedResponse(
            source="official-malaysia-gtfs-realtime",
            provider_key=provider.key,
            label=provider.label,
            vehicle_count=len(vehicles),
            feed_timestamp=feed_timestamp,
            vehicles=vehicles,
        )
        TransitService._live_cache[provider.key] = (now + float(settings.transit_realtime_cache_seconds), result)
        return result

    @staticmethod
    def get_nearby_live(
        latitude: float,
        longitude: float,
        radius_meters: float = 1000.0,
        provider_key: str | None = None,
        mode: str | None = "bus",
        query: str | None = None,
    ) -> TransitNearbyResponse:
        normalized_query = (query or "").strip().lower()
        providers = TransitService._providers_for_nearby(provider_key=provider_key, mode=mode)
        nearby_vehicles: list[TransitNearbyVehicleResponse] = []
        route_buckets: dict[tuple[str, str, str], TransitNearbyRouteResponse] = {}

        with ThreadPoolExecutor(max_workers=min(4, max(1, len(providers)))) as executor:
            future_map = {executor.submit(TransitService.get_live_feed, provider.key): provider for provider in providers}
            for future in as_completed(future_map):
                provider = future_map[future]
                try:
                    feed = future.result()
                except Exception:
                    continue
                for item in feed.vehicles:
                    distance_meters = TransitService._haversine_meters(
                        latitude,
                        longitude,
                        float(item.latitude),
                        float(item.longitude),
                    )
                    if distance_meters > radius_meters:
                        continue
                    haystack = " ".join(
                        part
                        for part in (
                            item.route_label or "",
                            item.route_id or "",
                            item.vehicle_id or "",
                            item.license_plate or "",
                            provider.label,
                        )
                        if part
                    ).lower()
                    if normalized_query and normalized_query not in haystack:
                        continue
                    nearby_vehicle = TransitNearbyVehicleResponse(
                        provider_key=provider.key,
                        provider_label=provider.label,
                        mode=provider.mode,
                        distance_meters=round(distance_meters, 1),
                        **item.model_dump(),
                    )
                    nearby_vehicles.append(nearby_vehicle)

                    route_label = item.route_label or item.route_id or item.trip_id or "Live nearby vehicle"
                    bucket_key = (provider.key, item.route_id or route_label, route_label)
                    existing = route_buckets.get(bucket_key)
                    if existing is None:
                        route_buckets[bucket_key] = TransitNearbyRouteResponse(
                            provider_key=provider.key,
                            provider_label=provider.label,
                            mode=provider.mode,
                            route_id=item.route_id,
                            route_label=route_label,
                            vehicle_count=1,
                            nearest_distance_meters=round(distance_meters, 1),
                        )
                    else:
                        existing.vehicle_count += 1
                        if existing.nearest_distance_meters is None or distance_meters < existing.nearest_distance_meters:
                            existing.nearest_distance_meters = round(distance_meters, 1)

        nearby_vehicles.sort(
            key=lambda item: (
                item.distance_meters,
                item.provider_label.lower(),
                (item.route_label or item.route_id or "").lower(),
                (item.license_plate or item.vehicle_id or "").lower(),
            )
        )
        routes = sorted(
            route_buckets.values(),
            key=lambda item: (
                item.nearest_distance_meters if item.nearest_distance_meters is not None else math.inf,
                item.provider_label.lower(),
                item.route_label.lower(),
            ),
        )

        return TransitNearbyResponse(
            source="official-malaysia-gtfs-realtime-nearby",
            latitude=latitude,
            longitude=longitude,
            radius_meters=radius_meters,
            providers_scanned=[provider.key for provider in providers],
            route_count=len(routes),
            vehicle_count=len(nearby_vehicles),
            routes=routes[:24],
            vehicles=nearby_vehicles[:80],
        )

    @staticmethod
    def _load_graph(network: str) -> TransitGraph:
        expires_in = max(settings.transit_static_cache_hours, 1) * 60 * 60
        cached = TransitService._graph_cache.get(network)
        now = time.monotonic()
        if cached and cached[0] > now:
            return cached[1]

        if network == "rapid-rail-kl":
            url = f"{TransitService.STATIC_BASE_URL}/prasarana?category=rapid-rail-kl"
        elif network == "ktmb":
            url = f"{TransitService.STATIC_BASE_URL}/ktmb"
        else:
            raise ValueError(f"Unsupported route-planning network `{network}`.")

        response = TransitService._client.get(url)
        response.raise_for_status()
        archive = zipfile.ZipFile(io.BytesIO(response.content))

        routes = TransitService._read_csv_from_zip(archive, "routes.txt")
        stops = TransitService._read_csv_from_zip(archive, "stops.txt")
        trips = TransitService._read_csv_from_zip(archive, "trips.txt")
        stop_times = TransitService._read_csv_from_zip(archive, "stop_times.txt")

        routes_by_id = {
            str(row.get("route_id", "")).strip(): {
                "route_short_name": str(row.get("route_short_name", "")).strip(),
                "route_long_name": str(row.get("route_long_name", "")).strip(),
                "route_desc": str(row.get("route_desc", "")).strip(),
                "route_color": str(row.get("route_color", "")).strip(),
            }
            for row in routes
            if str(row.get("route_id", "")).strip()
        }

        stops_by_id = {
            str(row.get("stop_id", "")).strip(): {
                "stop_name": str(row.get("stop_name", "")).strip(),
                "search": str(row.get("search", "")).strip(),
                "stop_lat": str(row.get("stop_lat", "")).strip(),
                "stop_lon": str(row.get("stop_lon", "")).strip(),
                "route_id": str(row.get("route_id", "")).strip(),
                "category": str(row.get("category", "")).strip(),
            }
            for row in stops
            if str(row.get("stop_id", "")).strip()
        }

        trip_route_map = {
            str(row.get("trip_id", "")).strip(): str(row.get("route_id", "")).strip()
            for row in trips
            if str(row.get("trip_id", "")).strip()
        }

        grouped_stop_times: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in stop_times:
            trip_id = str(row.get("trip_id", "")).strip()
            if trip_id:
                grouped_stop_times[trip_id].append(row)

        edge_map: dict[tuple[str, str, str | None, str], TransitEdge] = {}
        for trip_id, rows in grouped_stop_times.items():
            ordered = sorted(rows, key=lambda item: int(item.get("stop_sequence") or 0))
            route_id = trip_route_map.get(trip_id) or str((ordered[0] if ordered else {}).get("route_id", "")).strip()
            route_label = TransitService._route_label(route_id, routes_by_id)
            for index in range(len(ordered) - 1):
                current = ordered[index]
                nxt = ordered[index + 1]
                from_stop = str(current.get("stop_id", "")).strip()
                to_stop = str(nxt.get("stop_id", "")).strip()
                if not from_stop or not to_stop or from_stop == to_stop:
                    continue
                delta = TransitService._travel_minutes(
                    str(current.get("departure_time", "")).strip(),
                    str(nxt.get("arrival_time", "")).strip(),
                )
                key = (from_stop, to_stop, route_id or None, "ride")
                existing = edge_map.get(key)
                edge = TransitEdge(
                    to_stop_id=to_stop,
                    minutes=delta,
                    edge_type="ride",
                    route_id=route_id or None,
                    route_label=route_label,
                    from_stop_name=stops_by_id.get(from_stop, {}).get("stop_name"),
                    to_stop_name=stops_by_id.get(to_stop, {}).get("stop_name"),
                )
                if existing is None or edge.minutes < existing.minutes:
                    edge_map[key] = edge

        station_groups: dict[str, list[str]] = defaultdict(list)
        for stop_id, stop in stops_by_id.items():
            station_groups[stop["stop_name"]].append(stop_id)

        adjacency: dict[str, list[TransitEdge]] = defaultdict(list)
        for (from_stop, _, _, _), edge in edge_map.items():
            adjacency[from_stop].append(edge)

        for station_name, stop_ids in station_groups.items():
            TransitService._add_transfer_edges(
                adjacency=adjacency,
                stops_by_id=stops_by_id,
                stop_ids=stop_ids,
                minutes=6.0,
                label=station_name,
            )

        normalized_station_groups: dict[str, list[str]] = defaultdict(list)
        for stop_id, stop in stops_by_id.items():
            normalized_name = TransitService._normalize_stop_name(stop["stop_name"])
            if normalized_name:
                normalized_station_groups[normalized_name].append(stop_id)

        for normalized_name, stop_ids in normalized_station_groups.items():
            unique_station_names = {
                stops_by_id.get(stop_id, {}).get("stop_name", "")
                for stop_id in stop_ids
                if stops_by_id.get(stop_id, {}).get("stop_name")
            }
            if len(unique_station_names) <= 1:
                continue
            transfer_label = " / ".join(sorted(unique_station_names))
            TransitService._add_transfer_edges(
                adjacency=adjacency,
                stops_by_id=stops_by_id,
                stop_ids=stop_ids,
                minutes=4.0,
                label=transfer_label,
                cross_name_only=True,
            )

        graph = TransitGraph(
            network=network,
            source="official-malaysia-gtfs-static",
            stops_by_id=stops_by_id,
            routes_by_id=routes_by_id,
            adjacency=dict(adjacency),
            station_groups=dict(station_groups),
        )
        TransitService._graph_cache[network] = (now + expires_in, graph)
        return graph

    @staticmethod
    def _extract_origin_destination(text: str) -> tuple[str | None, str | None]:
        for pattern in (TransitService.FROM_TO_PATTERN, TransitService.TO_FROM_PATTERN, TransitService.BETWEEN_PATTERN):
            match = pattern.search(text)
            if not match:
                continue
            first = TransitService._clean_station_query(match.group(1))
            second = TransitService._clean_station_query(match.group(2))
            if pattern is TransitService.TO_FROM_PATTERN:
                return second, first
            return first, second
        return None, None

    @staticmethod
    def _clean_station_query(value: str) -> str:
        cleaned = re.sub(r"\b(?:by|via|using|on)\b.*$", "", value, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(?:faster|fastest|quicker|quickest|please|now|today)\b.*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^\b(?:the)\b\s+", "", cleaned, flags=re.IGNORECASE)
        return " ".join(cleaned.strip(" .,-").split())

    @staticmethod
    def _network_from_text(text: str) -> str:
        lowered = text.lower()
        if any(token in lowered for token in ("ktmb", "komuter", "ets")):
            return "ktmb"
        return "rapid-rail-kl"

    @staticmethod
    def _provider_from_text(text: str) -> TransitProvider | None:
        lowered = text.lower()
        if "ktmb" in lowered:
            return TransitService.PROVIDER_INDEX["ktmb"]
        if "mrt feeder" in lowered or "feeder bus" in lowered:
            return TransitService.PROVIDER_INDEX["prasarana:rapid-bus-mrtfeeder"]
        if "penang" in lowered:
            return TransitService.PROVIDER_INDEX["prasarana:rapid-bus-penang"]
        if "kuantan" in lowered:
            return TransitService.PROVIDER_INDEX["prasarana:rapid-bus-kuantan"]
        if "bus" in lowered and ("kl" in lowered or "kuala lumpur" in lowered or "rapid" in lowered):
            return TransitService.PROVIDER_INDEX["prasarana:rapid-bus-kl"]
        if any(token in lowered for token in ("lrt", "mrt", "monorail", "rapid rail")):
            return TransitService.PROVIDER_INDEX["rapid-rail-kl"]
        return None

    @staticmethod
    def _match_stations(query: str, graph: TransitGraph) -> list[str]:
        from difflib import SequenceMatcher

        query_norm = TransitService._normalize_stop_name(query)
        if not query_norm:
            return []

        exact = [name for name in graph.station_groups if TransitService._normalize_stop_name(name) == query_norm]
        if exact:
            return exact

        contains = [
            name
            for name in graph.station_groups
            if query_norm in TransitService._normalize_stop_name(name) or TransitService._normalize_stop_name(name) in query_norm
        ]
        if contains:
            contains.sort(key=lambda item: (len(TransitService._normalize_stop_name(item)), item))
            return contains[:5]

        scores: list[tuple[float, str]] = []
        for name, stop_ids in graph.station_groups.items():
            aliases = " ".join(graph.stops_by_id[stop_id].get("search", "") for stop_id in stop_ids)
            haystack = f"{name} {aliases}"
            score = SequenceMatcher(None, query_norm, TransitService._normalize_stop_name(haystack)).ratio()
            scores.append((score, name))
        scores.sort(key=lambda item: (-item[0], item[1]))
        return [name for score, name in scores[:5] if score >= 0.55]

    @staticmethod
    def _shortest_path(graph: TransitGraph, origin_stop: str, destination_stop: str) -> tuple[float, list[TransitEdge]] | None:
        queue: list[tuple[float, str]] = [(0.0, origin_stop)]
        distances: dict[str, float] = {origin_stop: 0.0}
        previous: dict[str, tuple[str, TransitEdge]] = {}

        while queue:
            minutes, stop_id = heappop(queue)
            if stop_id == destination_stop:
                break
            if minutes > distances.get(stop_id, math.inf):
                continue
            for edge in graph.adjacency.get(stop_id, []):
                next_minutes = minutes + edge.minutes
                if next_minutes >= distances.get(edge.to_stop_id, math.inf):
                    continue
                distances[edge.to_stop_id] = next_minutes
                previous[edge.to_stop_id] = (stop_id, edge)
                heappush(queue, (next_minutes, edge.to_stop_id))

        if destination_stop not in distances:
            return None

        edges: list[TransitEdge] = []
        cursor = destination_stop
        while cursor != origin_stop:
            prev = previous.get(cursor)
            if prev is None:
                break
            prior_stop, edge = prev
            edges.append(edge)
            cursor = prior_stop
        edges.reverse()
        return distances[destination_stop], edges

    @staticmethod
    def _build_route_steps(edges: list[TransitEdge]) -> list[TransitRouteStepResponse]:
        if not edges:
            return []

        steps: list[TransitRouteStepResponse] = []
        current_edges: list[TransitEdge] = []
        current_key = (edges[0].edge_type, edges[0].route_id)

        def flush() -> None:
            if not current_edges:
                return
            first = current_edges[0]
            last = current_edges[-1]
            total = round(sum(item.minutes for item in current_edges), 1)
            if first.edge_type == "transfer":
                transfer_origin = first.from_stop_name or ""
                transfer_destination = last.to_stop_name or first.to_stop_name or ""
                if transfer_origin and transfer_destination and transfer_origin != transfer_destination:
                    instruction = f"Transfer between {transfer_origin} and {transfer_destination}."
                else:
                    instruction = f"Transfer at {transfer_origin or transfer_destination}."
                steps.append(
                    TransitRouteStepResponse(
                        step_type="transfer",
                        instruction=instruction,
                        from_stop=transfer_origin,
                        to_stop=transfer_destination,
                        route_id=None,
                        route_label="Transfer",
                        stop_count=0,
                        estimated_minutes=total,
                    )
                )
                return
            route_label = first.route_label or first.route_id or "the line"
            steps.append(
                TransitRouteStepResponse(
                    step_type="ride",
                    instruction=(
                        f"Ride {route_label} from {first.from_stop_name or ''} to {last.to_stop_name or ''} "
                        f"for {len(current_edges)} stop{'s' if len(current_edges) != 1 else ''} "
                        f"(about {round(total)} min)."
                    ),
                    from_stop=first.from_stop_name or "",
                    to_stop=last.to_stop_name or "",
                    route_id=first.route_id,
                    route_label=route_label,
                    stop_count=len(current_edges),
                    estimated_minutes=total,
                )
            )

        for edge in edges:
            key = (edge.edge_type, edge.route_id)
            if key != current_key:
                flush()
                current_edges = [edge]
                current_key = key
            else:
                current_edges.append(edge)
        flush()
        return steps

    @staticmethod
    def _build_live_url(provider: TransitProvider) -> str:
        if provider.agency == "prasarana":
            return f"{TransitService.REALTIME_BASE_URL}/prasarana?category={provider.category}"
        return f"{TransitService.REALTIME_BASE_URL}/{provider.category or provider.key}"

    @staticmethod
    def _route_label_lookup_for_provider(provider: TransitProvider) -> dict[str, str]:
        static_category = provider.static_category
        if not static_category:
            return {}
        cached = TransitService._route_label_cache.get(provider.key)
        now = time.monotonic()
        if cached and cached[0] > now:
            return cached[1]
        try:
            if provider.agency == "prasarana":
                url = f"{TransitService.STATIC_BASE_URL}/prasarana?category={static_category}"
            else:
                url = f"{TransitService.STATIC_BASE_URL}/{static_category}"
            response = TransitService._client.get(url)
            response.raise_for_status()
            archive = zipfile.ZipFile(io.BytesIO(response.content))
            routes = TransitService._read_csv_from_zip(archive, "routes.txt")
            trip_route_map: dict[str, str] = {}
            try:
                trips = TransitService._read_csv_from_zip(archive, "trips.txt")
                trip_route_map = {
                    str(row.get("trip_id", "")).strip(): str(row.get("route_id", "")).strip()
                    for row in trips
                    if str(row.get("trip_id", "")).strip() and str(row.get("route_id", "")).strip()
                }
            except Exception:
                trip_route_map = {}
            labels = {
                str(row.get("route_id", "")).strip(): TransitService._route_label(
                    str(row.get("route_id", "")).strip(),
                    {
                        str(row.get("route_id", "")).strip(): {
                            "route_short_name": str(row.get("route_short_name", "")).strip(),
                            "route_long_name": str(row.get("route_long_name", "")).strip(),
                        }
                    },
                )
                for row in routes
                if str(row.get("route_id", "")).strip()
            }
            for trip_id, route_id in trip_route_map.items():
                if route_id in labels:
                    labels[f"trip:{trip_id}"] = labels[route_id]
            TransitService._route_label_cache[provider.key] = (
                now + max(settings.transit_static_cache_hours, 1) * 60 * 60,
                labels,
            )
            return labels
        except Exception:
            return {}

    @staticmethod
    def _read_csv_from_zip(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
        with archive.open(name) as handle:
            return list(csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig")))

    @staticmethod
    def _route_label(route_id: str, routes_by_id: dict[str, dict[str, str]]) -> str:
        meta = routes_by_id.get(route_id, {})
        short_name = meta.get("route_short_name", "")
        long_name = meta.get("route_long_name", "")
        if short_name and long_name:
            return f"{long_name} ({short_name})"
        return long_name or short_name or route_id

    @staticmethod
    def _travel_minutes(departure_time: str, arrival_time: str) -> float:
        dep = TransitService._parse_gtfs_minutes(departure_time)
        arr = TransitService._parse_gtfs_minutes(arrival_time)
        delta = arr - dep
        if delta <= 0:
            return 2.5
        return max(1.0, float(delta))

    @staticmethod
    def _parse_gtfs_minutes(value: str) -> int:
        parts = [int(item) for item in value.split(":")]
        if len(parts) != 3:
            return 0
        return parts[0] * 60 + parts[1] + int(round(parts[2] / 60))

    @staticmethod
    def _normalize_stop_name(value: str) -> str:
        lowered = value.lower()
        lowered = re.sub(r"\b(?:stesen|station|lrt|mrt|monorail|ktm|komuter|line)\b", " ", lowered)
        lowered = re.sub(r"[^a-z0-9]+", "", lowered)
        return lowered

    @staticmethod
    def _add_transfer_edges(
        adjacency: dict[str, list[TransitEdge]],
        stops_by_id: dict[str, dict[str, str]],
        stop_ids: list[str],
        minutes: float,
        label: str,
        cross_name_only: bool = False,
    ) -> None:
        unique = list(dict.fromkeys(stop_ids))
        if len(unique) <= 1:
            return
        for from_id in unique:
            from_name = stops_by_id.get(from_id, {}).get("stop_name") or ""
            for to_id in unique:
                if from_id == to_id:
                    continue
                to_name = stops_by_id.get(to_id, {}).get("stop_name") or ""
                if cross_name_only and from_name == to_name:
                    continue
                adjacency[from_id].append(
                    TransitEdge(
                        to_stop_id=to_id,
                        minutes=minutes,
                        edge_type="transfer",
                        route_label="Transfer",
                        from_stop_name=from_name or label,
                        to_stop_name=to_name or label,
                    )
                )

    @staticmethod
    def _providers_for_nearby(provider_key: str | None = None, mode: str | None = "bus") -> list[TransitProvider]:
        if provider_key:
            provider = TransitService.PROVIDER_INDEX.get(provider_key)
            if provider is None:
                raise ValueError(f"Unknown transit provider `{provider_key}`.")
            if not provider.live_supported:
                raise ValueError(f"{provider.label} does not currently expose a stable official realtime feed.")
            return [provider]

        candidates = [
            provider
            for provider in TransitService.PROVIDERS
            if provider.live_supported and (mode is None or provider.mode == mode)
        ]
        preferred_order = [
            "prasarana:rapid-bus-kl",
            "prasarana:rapid-bus-mrtfeeder",
            "prasarana:rapid-bus-penang",
            "prasarana:rapid-bus-kuantan",
            "ktmb",
        ]
        order_index = {key: idx for idx, key in enumerate(preferred_order)}
        candidates.sort(key=lambda item: (order_index.get(item.key, 999), item.label))
        return candidates

    @staticmethod
    def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius = 6371000.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        a = (
            math.sin(delta_phi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        )
        return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))
