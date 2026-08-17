"""Load and query the directed road graph that represents the city."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.models import Intersection, NetworkValidationError, Road


class RoadNetwork:
    """Store a validated directed graph of intersections and outgoing roads.

    I use an adjacency list because route-finding repeatedly needs roads leaving
    one intersection. It is compact and is the structure Dijkstra's algorithm
    will use in the next step.
    """

    def __init__(
        self, intersections: Iterable[Intersection], roads: Iterable[Road]
    ) -> None:
        """Build lookup tables and catch invalid references as early as possible."""
        self._intersections = self._index_intersections(intersections)
        self._roads = self._index_roads(roads)
        self._outgoing_roads: dict[str, tuple[Road, ...]] = self._build_adjacency()

    @classmethod
    def from_json_file(cls, map_path: Path) -> "RoadNetwork":
        """Read a city-map JSON file and convert it into a validated graph."""
        try:
            raw_map = json.loads(map_path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise NetworkValidationError(f"City map was not found: {map_path}") from error
        except json.JSONDecodeError as error:
            raise NetworkValidationError(
                f"City map contains invalid JSON: {map_path}"
            ) from error

        if not isinstance(raw_map, dict):
            raise NetworkValidationError("The city map must contain one JSON object.")

        intersections = cls._parse_intersections(raw_map.get("intersections"))
        roads = cls._parse_roads(raw_map.get("roads"))
        return cls(intersections=intersections, roads=roads)

    @property
    def intersection_count(self) -> int:
        """Return the number of junctions available to the simulation."""
        return len(self._intersections)

    @property
    def road_count(self) -> int:
        """Return the number of directed road segments in the city graph."""
        return len(self._roads)

    @property
    def intersection_ids(self) -> tuple[str, ...]:
        """Return stable intersection ids when another component needs every node."""
        return tuple(self._intersections)

    @property
    def roads(self) -> tuple[Road, ...]:
        """Return all roads in map order for simulation-wide calculations."""
        return tuple(self._roads.values())

    def get_intersection(self, intersection_id: str) -> Intersection:
        """Return one junction or explain clearly when its id is unknown."""
        try:
            return self._intersections[intersection_id]
        except KeyError as error:
            raise NetworkValidationError(
                f"Unknown intersection id: '{intersection_id}'."
            ) from error

    def get_road(self, road_id: str) -> Road:
        """Return one directed road or explain clearly when its id is unknown."""
        try:
            return self._roads[road_id]
        except KeyError as error:
            raise NetworkValidationError(f"Unknown road id: '{road_id}'.") from error

    def outgoing_roads(self, intersection_id: str) -> tuple[Road, ...]:
        """Return every road that a vehicle may take from one intersection."""
        self.get_intersection(intersection_id)
        return self._outgoing_roads[intersection_id]

    def _index_intersections(
        self, intersections: Iterable[Intersection]
    ) -> dict[str, Intersection]:
        """Index intersections by id while preventing ambiguous duplicate nodes."""
        indexed: dict[str, Intersection] = {}
        for intersection in intersections:
            if intersection.id in indexed:
                raise NetworkValidationError(
                    f"Duplicate intersection id: '{intersection.id}'."
                )
            indexed[intersection.id] = intersection

        if not indexed:
            raise NetworkValidationError("The city map needs at least one intersection.")
        return indexed

    def _index_roads(self, roads: Iterable[Road]) -> dict[str, Road]:
        """Index roads by id and make sure both endpoints exist in the map."""
        indexed: dict[str, Road] = {}
        for road in roads:
            if road.id in indexed:
                raise NetworkValidationError(f"Duplicate road id: '{road.id}'.")
            if road.source_id not in self._intersections:
                raise NetworkValidationError(
                    f"Road '{road.id}' references unknown source '{road.source_id}'."
                )
            if road.destination_id not in self._intersections:
                raise NetworkValidationError(
                    f"Road '{road.id}' references unknown destination "
                    f"'{road.destination_id}'."
                )
            indexed[road.id] = road
        return indexed

    def _build_adjacency(self) -> dict[str, tuple[Road, ...]]:
        """Group roads by source node for fast route-expansion later."""
        grouped: defaultdict[str, list[Road]] = defaultdict(list)
        for road in self._roads.values():
            grouped[road.source_id].append(road)
        return {
            intersection_id: tuple(grouped[intersection_id])
            for intersection_id in self._intersections
        }

    @staticmethod
    def _parse_intersections(raw_intersections: Any) -> list[Intersection]:
        """Turn JSON intersection records into typed, validated objects."""
        if not isinstance(raw_intersections, list):
            raise NetworkValidationError("'intersections' must be a JSON list.")

        parsed: list[Intersection] = []
        for raw_intersection in raw_intersections:
            if not isinstance(raw_intersection, dict):
                raise NetworkValidationError("Each intersection must be a JSON object.")
            try:
                parsed.append(
                    Intersection(
                        id=str(raw_intersection["id"]),
                        x=float(raw_intersection["x"]),
                        y=float(raw_intersection["y"]),
                    )
                )
            except (KeyError, TypeError, ValueError) as error:
                raise NetworkValidationError(
                    "Each intersection needs an id and numeric x/y coordinates."
                ) from error
        return parsed

    @staticmethod
    def _parse_roads(raw_roads: Any) -> list[Road]:
        """Turn JSON road records into typed, validated directed road segments."""
        if not isinstance(raw_roads, list):
            raise NetworkValidationError("'roads' must be a JSON list.")

        parsed: list[Road] = []
        for raw_road in raw_roads:
            if not isinstance(raw_road, dict):
                raise NetworkValidationError("Each road must be a JSON object.")
            try:
                parsed.append(
                    Road(
                        id=str(raw_road["id"]),
                        source_id=str(raw_road["from"]),
                        destination_id=str(raw_road["to"]),
                        length_meters=float(raw_road["lengthMeters"]),
                        speed_limit_kmph=float(raw_road["speedLimitKmph"]),
                        lanes=int(raw_road["lanes"]),
                        capacity=int(raw_road["capacity"]),
                    )
                )
            except (KeyError, TypeError, ValueError) as error:
                raise NetworkValidationError(
                    "Each road needs id, from, to, lengthMeters, speedLimitKmph, "
                    "lanes, and capacity values."
                ) from error
        return parsed
