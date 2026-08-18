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


class SignalStrategy(StrEnum):
    """Name the fixed and queue-aware signal-control policies the project compares."""

    FIXED = "fixed"
    ADAPTIVE = "adaptive"


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
    """Run one intersection with either fixed timing or queue-aware green timing.

    I keep yellow as a non-entry phase in this first version. That is a simple,
    safe rule: a vehicle at the stop line waits until it receives a full green.
    """

    intersection_id: str
    green_seconds: int = 20
    yellow_seconds: int = 3
    strategy: SignalStrategy = SignalStrategy.FIXED
    minimum_green_seconds: int = 8
    maximum_green_seconds: int = 30
    phase: SignalPhase = SignalPhase.HORIZONTAL_GREEN
    elapsed_phase_seconds: float = field(default=0.0, init=False)
    next_green_axis: SignalAxis = field(default=SignalAxis.VERTICAL, init=False)

    def __post_init__(self) -> None:
        """Reject a timing plan that could not advance through a real cycle."""
        if not self.intersection_id.strip():
            raise NetworkValidationError("A signal must belong to an intersection.")
        if self.green_seconds < 1:
            raise NetworkValidationError("Signal green time must be at least one second.")
        if self.yellow_seconds < 1:
            raise NetworkValidationError("Signal yellow time must be at least one second.")
        if self.minimum_green_seconds < 1:
            raise NetworkValidationError("Adaptive minimum green time must be positive.")
        if self.maximum_green_seconds < self.minimum_green_seconds:
            raise NetworkValidationError(
                "Adaptive maximum green time must not be below its minimum green time."
            )

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
            return (
                self.green_seconds
                if self.strategy is SignalStrategy.FIXED
                else self.maximum_green_seconds
            )
        return self.yellow_seconds

    def advance(
        self,
        seconds: float,
        queued_by_axis: dict[SignalAxis, int] | None = None,
    ) -> None:
        """Move the signal clock forward using its configured control strategy.

        Fixed signals retain a predictable cycle. Adaptive signals keep green for
        at least the configured minimum, then choose the axis with the larger
        queue while enforcing a maximum green duration.
        """
        if seconds < 0:
            raise NetworkValidationError("Signal time cannot move backwards.")

        if self.strategy is SignalStrategy.ADAPTIVE:
            if not float(seconds).is_integer():
                raise NetworkValidationError(
                    "Adaptive signal time must advance in whole-second ticks."
                )
            queues = queued_by_axis or {}
            for _ in range(int(seconds)):
                self._advance_adaptive_tick(queues)
            return

        remaining_seconds = seconds
        while remaining_seconds > 0:
            available_seconds = self._phase_duration - self.elapsed_phase_seconds
            consumed_seconds = min(remaining_seconds, available_seconds)
            self.elapsed_phase_seconds += consumed_seconds
            remaining_seconds -= consumed_seconds

            if self.elapsed_phase_seconds >= self._phase_duration:
                self.phase = _PHASE_ORDER[(_PHASE_ORDER.index(self.phase) + 1) % 4]
                self.elapsed_phase_seconds = 0.0

    def _advance_adaptive_tick(self, queued_by_axis: dict[SignalAxis, int]) -> None:
        """Make one queue-aware timing decision while preserving yellow clearance."""
        if self.active_axis is None:
            self.elapsed_phase_seconds += 1.0
            if self.elapsed_phase_seconds >= self.yellow_seconds:
                self.phase = (
                    SignalPhase.HORIZONTAL_GREEN
                    if self.next_green_axis is SignalAxis.HORIZONTAL
                    else SignalPhase.VERTICAL_GREEN
                )
                self.elapsed_phase_seconds = 0.0
            return

        self.elapsed_phase_seconds += 1.0
        if self.elapsed_phase_seconds < self.minimum_green_seconds:
            return

        active_axis = self.active_axis
        other_axis = (
            SignalAxis.VERTICAL
            if active_axis is SignalAxis.HORIZONTAL
            else SignalAxis.HORIZONTAL
        )
        active_queue = queued_by_axis.get(active_axis, 0)
        other_queue = queued_by_axis.get(other_axis, 0)

        if other_queue > active_queue:
            self._start_yellow_for(other_axis)
            return

        if self.elapsed_phase_seconds >= self.maximum_green_seconds:
            selected_axis = self._preferred_axis(active_axis, other_axis, queued_by_axis)
            if selected_axis is active_axis:
                self.elapsed_phase_seconds = 0.0
            else:
                self._start_yellow_for(selected_axis)

    def _preferred_axis(
        self,
        active_axis: SignalAxis,
        other_axis: SignalAxis,
        queued_by_axis: dict[SignalAxis, int],
    ) -> SignalAxis:
        """Choose the longer queue, alternating ties to avoid starving an approach."""
        active_queue = queued_by_axis.get(active_axis, 0)
        other_queue = queued_by_axis.get(other_axis, 0)
        if other_queue >= active_queue:
            return other_axis
        return active_axis

    def _start_yellow_for(self, next_axis: SignalAxis) -> None:
        """Leave green safely before opening the selected queued direction."""
        self.next_green_axis = next_axis
        self.phase = (
            SignalPhase.HORIZONTAL_YELLOW
            if self.active_axis is SignalAxis.HORIZONTAL
            else SignalPhase.VERTICAL_YELLOW
        )
        self.elapsed_phase_seconds = 0.0

    def allows(self, incoming_road: Road, network: RoadNetwork) -> bool:
        """Check whether the road approaching this light matches its green axis."""
        if incoming_road.destination_id != self.intersection_id:
            raise NetworkValidationError(
                f"Road '{incoming_road.id}' does not enter signal "
                f"'{self.intersection_id}'."
            )
        return self.active_axis is road_axis(incoming_road, network)

    def request_priority(self, axis: SignalAxis) -> None:
        """Pre-empt the current phase for an emergency approach at this signal."""
        if self.active_axis is axis:
            return
        self.phase = (
            SignalPhase.HORIZONTAL_GREEN
            if axis is SignalAxis.HORIZONTAL
            else SignalPhase.VERTICAL_GREEN
        )
        self.elapsed_phase_seconds = 0.0
        self.next_green_axis = (
            SignalAxis.VERTICAL if axis is SignalAxis.HORIZONTAL else SignalAxis.HORIZONTAL
        )

    def as_dict(self) -> dict[str, str | float | None]:
        """Return the current light state in a shape that the dashboard can consume."""
        return {
            "intersectionId": self.intersection_id,
            "strategy": self.strategy.value,
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
