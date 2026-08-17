"""Fixed-time traffic-signal behaviour for the first simulation version."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.graph import RoadNetwork
from app.models import NetworkValidationError, Road


class SignalAxis(StrEnum):
    """Name the two traffic directions available in the starter grid map."""

    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class SignalPhase(StrEnum):
    """List the repeating phases used by every fixed-time signal controller."""

    HORIZONTAL_GREEN = "horizontal_green"
    HORIZONTAL_YELLOW = "horizontal_yellow"
    VERTICAL_GREEN = "vertical_green"
    VERTICAL_YELLOW = "vertical_yellow"


_PHASE_ORDER = (
    SignalPhase.HORIZONTAL_GREEN,
    SignalPhase.HORIZONTAL_YELLOW,
    SignalPhase.VERTICAL_GREEN,
    SignalPhase.VERTICAL_YELLOW,
)


@dataclass(slots=True)
class FixedTimeSignal:
    """Run one intersection through a predictable horizontal/vertical light cycle.

    I keep yellow as a non-entry phase in this first version. That is a simple,
    safe rule: a vehicle at the stop line waits until it receives a full green.
    """

    intersection_id: str
    green_seconds: int = 20
    yellow_seconds: int = 3
    phase: SignalPhase = SignalPhase.HORIZONTAL_GREEN
    elapsed_phase_seconds: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        """Reject a timing plan that could not advance through a real cycle."""
        if not self.intersection_id.strip():
            raise NetworkValidationError("A signal must belong to an intersection.")
        if self.green_seconds < 1:
            raise NetworkValidationError("Signal green time must be at least one second.")
        if self.yellow_seconds < 1:
            raise NetworkValidationError("Signal yellow time must be at least one second.")

    @property
    def active_axis(self) -> SignalAxis | None:
        """Return the only direction currently allowed to enter the intersection."""
        if self.phase is SignalPhase.HORIZONTAL_GREEN:
            return SignalAxis.HORIZONTAL
        if self.phase is SignalPhase.VERTICAL_GREEN:
            return SignalAxis.VERTICAL
        return None

    @property
    def seconds_until_next_phase(self) -> float:
        """Show the remaining time for dashboard labels and API snapshots."""
        return self._phase_duration - self.elapsed_phase_seconds

    @property
    def _phase_duration(self) -> int:
        """Choose the configured duration for the controller's current phase."""
        if self.phase in {
            SignalPhase.HORIZONTAL_GREEN,
            SignalPhase.VERTICAL_GREEN,
        }:
            return self.green_seconds
        return self.yellow_seconds

    def advance(self, seconds: float) -> None:
        """Move the signal clock forward while preserving every phase transition."""
        if seconds < 0:
            raise NetworkValidationError("Signal time cannot move backwards.")

        remaining_seconds = seconds
        while remaining_seconds > 0:
            available_seconds = self._phase_duration - self.elapsed_phase_seconds
            consumed_seconds = min(remaining_seconds, available_seconds)
            self.elapsed_phase_seconds += consumed_seconds
            remaining_seconds -= consumed_seconds

            if self.elapsed_phase_seconds >= self._phase_duration:
                self.phase = _PHASE_ORDER[(_PHASE_ORDER.index(self.phase) + 1) % 4]
                self.elapsed_phase_seconds = 0.0

    def allows(self, incoming_road: Road, network: RoadNetwork) -> bool:
        """Check whether the road approaching this light matches its green axis."""
        if incoming_road.destination_id != self.intersection_id:
            raise NetworkValidationError(
                f"Road '{incoming_road.id}' does not enter signal "
                f"'{self.intersection_id}'."
            )
        return self.active_axis is road_axis(incoming_road, network)

    def as_dict(self) -> dict[str, str | float | None]:
        """Return the current light state in a shape that the dashboard can consume."""
        return {
            "intersectionId": self.intersection_id,
            "phase": self.phase.value,
            "activeAxis": self.active_axis.value if self.active_axis else None,
            "secondsUntilNextPhase": round(self.seconds_until_next_phase, 2),
        }


def road_axis(road: Road, network: RoadNetwork) -> SignalAxis:
    """Classify a grid road by the direction from which a vehicle approaches."""
    source = network.get_intersection(road.source_id)
    destination = network.get_intersection(road.destination_id)
    if source.y == destination.y and source.x != destination.x:
        return SignalAxis.HORIZONTAL
    if source.x == destination.x and source.y != destination.y:
        return SignalAxis.VERTICAL
    raise NetworkValidationError(
        f"Road '{road.id}' is diagonal or zero-length and cannot use the "
        "starter two-axis signal controller."
    )
