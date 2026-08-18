"""Typed data models for the city map used by the traffic simulation."""

from __future__ import annotations

from dataclasses import dataclass


class NetworkValidationError(ValueError):
    """Explain why I could not safely use a city-map configuration."""


@dataclass(frozen=True, slots=True)
class Intersection:
    """Represent one road junction and its canvas position in the city map.

    I keep coordinates on the intersection rather than calculating them from the
    graph, because the dashboard needs a stable place to draw every junction.
    """

    id: str
    x: float
    y: float

    def __post_init__(self) -> None:
        """Reject unnamed intersections before they can enter the graph."""
        if not self.id.strip():
            raise NetworkValidationError("An intersection id cannot be empty.")

    def as_dict(self) -> dict[str, str | float]:
        """Return the coordinates in the compact shape used by the map canvas."""
        return {"id": self.id, "x": self.x, "y": self.y}


@dataclass(frozen=True, slots=True)
class Road:
    """Represent a directed road segment between two intersections.

    Each direction is stored as its own road. This lets me model unequal traffic
    and different conditions for the two sides of the same physical street.
    """

    id: str
    source_id: str
    destination_id: str
    length_meters: float
    speed_limit_kmph: float
    lanes: int
    capacity: int

    def __post_init__(self) -> None:
        """Validate values that would otherwise produce impossible travel times."""
        if not self.id.strip():
            raise NetworkValidationError("A road id cannot be empty.")
        if not self.source_id.strip() or not self.destination_id.strip():
            raise NetworkValidationError(
                f"Road '{self.id}' must have a source and destination."
            )
        if self.length_meters <= 0:
            raise NetworkValidationError(
                f"Road '{self.id}' must have a positive length."
            )
        if self.speed_limit_kmph <= 0:
            raise NetworkValidationError(
                f"Road '{self.id}' must have a positive speed limit."
            )
        if self.lanes < 1:
            raise NetworkValidationError(f"Road '{self.id}' needs at least one lane.")
        if self.capacity < 1:
            raise NetworkValidationError(
                f"Road '{self.id}' needs a positive vehicle capacity."
            )

    @property
    def base_travel_time_seconds(self) -> float:
        """Return free-flow travel time before congestion penalties are applied."""
        speed_meters_per_second = self.speed_limit_kmph / 3.6
        return self.length_meters / speed_meters_per_second

    def as_dict(self) -> dict[str, str | float | int]:
        """Return public road details without exposing the dataclass implementation."""
        return {
            "id": self.id,
            "from": self.source_id,
            "to": self.destination_id,
            "lengthMeters": self.length_meters,
            "speedLimitKmph": self.speed_limit_kmph,
            "lanes": self.lanes,
            "capacity": self.capacity,
        }
