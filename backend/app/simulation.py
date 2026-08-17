"""One-second vehicle movement for the first traffic-flow simulation."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

from app.congestion import congested_travel_time_seconds, density_ratio
from app.graph import RoadNetwork
from app.models import NetworkValidationError, Road
from app.routing import Route, find_shortest_route
from app.signals import FixedTimeSignal


class VehicleStatus(StrEnum):
    """Describe whether a vehicle is moving, queued, or has finished its trip."""

    MOVING = "moving"
    WAITING = "waiting"
    COMPLETED = "completed"


class WaitingReason(StrEnum):
    """Record why a queued vehicle cannot yet enter its next road."""

    SIGNAL = "signal"
    ROAD_CAPACITY = "road_capacity"


@dataclass(slots=True)
class Vehicle:
    """Keep the route progress and timing data for one simulated vehicle.

    Vehicles still use point-like positions, but they now remain on their current
    road when a red light or a full downstream road forms a queue.
    """

    id: str
    route: Route
    current_road_index: int = 0
    position_meters: float = 0.0
    status: VehicleStatus = VehicleStatus.MOVING
    travel_time_seconds: float = 0.0
    waiting_time_seconds: float = 0.0
    waiting_reason: WaitingReason | None = None

    @property
    def current_road_id(self) -> str | None:
        """Return the road currently occupied, or none after the trip is complete."""
        if self.status is VehicleStatus.COMPLETED:
            return None
        return self.route.road_ids[self.current_road_index]

    def as_dict(self) -> dict[str, str | float | int | None]:
        """Return only the state needed by an API client or visual dashboard."""
        return {
            "id": self.id,
            "status": self.status.value,
            "currentRoadId": self.current_road_id,
            "currentRoadIndex": self.current_road_index,
            "positionMeters": round(self.position_meters, 2),
            "travelTimeSeconds": round(self.travel_time_seconds, 2),
            "waitingTimeSeconds": round(self.waiting_time_seconds, 2),
            "waitingReason": self.waiting_reason.value if self.waiting_reason else None,
            "source": self.route.source_id,
            "destination": self.route.destination_id,
        }


class TrafficSimulation:
    """Advance vehicles over a road network in fixed, deterministic time steps.

    I update every signal before evaluating vehicles in a tick. I also keep road
    occupancy current as cars leave or enter, so no road can exceed its capacity.
    """

    def __init__(
        self,
        network: RoadNetwork,
        signals: dict[str, FixedTimeSignal] | None = None,
    ) -> None:
        """Create a simulation with fixed-time signals at every map intersection."""
        self.network = network
        self.signals = {
            intersection_id: FixedTimeSignal(intersection_id)
            for intersection_id in network.intersection_ids
        }
        if signals:
            for intersection_id, signal in signals.items():
                network.get_intersection(intersection_id)
                if signal.intersection_id != intersection_id:
                    raise NetworkValidationError(
                        "A signal dictionary key must match the signal intersection id."
                    )
                self.signals[intersection_id] = signal

        self.vehicles: dict[str, Vehicle] = {}
        self.elapsed_seconds = 0.0

    def add_vehicle(self, vehicle_id: str, source_id: str, destination_id: str) -> Vehicle:
        """Plan a congestion-aware route and place a vehicle on its first road."""
        if not vehicle_id.strip():
            raise NetworkValidationError("A vehicle id cannot be empty.")
        if vehicle_id in self.vehicles:
            raise NetworkValidationError(f"Vehicle id '{vehicle_id}' already exists.")

        route = find_shortest_route(
            self.network,
            source_id,
            destination_id,
            road_cost=self._congestion_aware_cost,
        )
        if route.road_ids:
            first_road = self.network.get_road(route.road_ids[0])
            if self._road_occupancies()[first_road.id] >= first_road.capacity:
                raise NetworkValidationError(
                    f"Cannot add '{vehicle_id}': first road '{first_road.id}' is full."
                )
        vehicle = Vehicle(id=vehicle_id, route=route)
        if not route.road_ids:
            vehicle.status = VehicleStatus.COMPLETED
        self.vehicles[vehicle_id] = vehicle
        return vehicle

    def advance(self, seconds: float = 1.0) -> None:
        """Run a whole-number number of one-second simulation ticks."""
        if seconds <= 0 or not float(seconds).is_integer():
            raise NetworkValidationError("Simulation advances must use whole positive seconds.")

        for _ in range(int(seconds)):
            for signal in self.signals.values():
                signal.advance(1.0)
            occupancies = self._road_occupancies()
            for vehicle in self.vehicles.values():
                self._advance_vehicle(vehicle, occupancies)
            self.elapsed_seconds += 1.0

    def snapshot(self) -> dict[str, object]:
        """Capture the current simulation state without exposing mutable objects."""
        occupancies = self._road_occupancies()
        status_counts = {status.value: 0 for status in VehicleStatus}
        for vehicle in self.vehicles.values():
            status_counts[vehicle.status.value] += 1

        return {
            "elapsedSeconds": self.elapsed_seconds,
            "vehicles": [vehicle.as_dict() for vehicle in self.vehicles.values()],
            "signals": [signal.as_dict() for signal in self.signals.values()],
            "roads": [self._road_state(road, occupancies[road.id]) for road in self.network.roads],
            "queueLengths": self._queue_lengths(),
            "vehicleCounts": status_counts,
            "metrics": self._metrics(occupancies),
        }

    def _advance_vehicle(self, vehicle: Vehicle, occupancies: Counter[str]) -> None:
        """Move one vehicle through one tick or account for its signal waiting time."""
        if vehicle.status is VehicleStatus.COMPLETED:
            return

        road = self._current_road(vehicle)
        vehicle.travel_time_seconds += 1.0

        if vehicle.status is VehicleStatus.WAITING:
            self._leave_intersection_if_possible(vehicle, road, occupancies)
            return

        distance_this_tick = road.speed_limit_kmph / 3.6
        vehicle.position_meters += distance_this_tick
        if vehicle.position_meters < road.length_meters:
            return

        vehicle.position_meters = road.length_meters
        if vehicle.current_road_index == len(vehicle.route.road_ids) - 1:
            vehicle.status = VehicleStatus.COMPLETED
            occupancies[road.id] -= 1
            return

        self._leave_intersection_if_possible(vehicle, road, occupancies)

    def _leave_intersection_if_possible(
        self, vehicle: Vehicle, current_road: Road, occupancies: Counter[str]
    ) -> None:
        """Move a queued car onward only when its signal and next-road capacity allow it."""
        next_road = self.network.get_road(
            vehicle.route.road_ids[vehicle.current_road_index + 1]
        )
        signal_is_green = self.signals[current_road.destination_id].allows(
            current_road, self.network
        )
        if not signal_is_green:
            self._queue_vehicle(vehicle, WaitingReason.SIGNAL)
            return
        if occupancies[next_road.id] >= next_road.capacity:
            self._queue_vehicle(vehicle, WaitingReason.ROAD_CAPACITY)
            return

        occupancies[current_road.id] -= 1
        occupancies[next_road.id] += 1
        vehicle.current_road_index += 1
        vehicle.position_meters = 0.0
        vehicle.status = VehicleStatus.MOVING
        vehicle.waiting_reason = None

    def _queue_vehicle(self, vehicle: Vehicle, reason: WaitingReason) -> None:
        """Keep a vehicle at the stop line and add one second to its queue time."""
        vehicle.status = VehicleStatus.WAITING
        vehicle.waiting_reason = reason
        vehicle.waiting_time_seconds += 1.0

    def _road_occupancies(self) -> Counter[str]:
        """Count every active vehicle against the capacity of its current road."""
        return Counter(
            vehicle.current_road_id
            for vehicle in self.vehicles.values()
            if vehicle.current_road_id is not None
        )

    def _queue_lengths(self) -> dict[str, int]:
        """Count vehicles waiting at the downstream end of each road."""
        queues = Counter(
            vehicle.current_road_id
            for vehicle in self.vehicles.values()
            if vehicle.status is VehicleStatus.WAITING and vehicle.current_road_id is not None
        )
        return dict(queues)

    def _congestion_aware_cost(self, road: Road) -> float:
        """Prefer roads with lower current density when planning a new trip route."""
        occupancy = self._road_occupancies()[road.id]
        travel_time = congested_travel_time_seconds(road, occupancy)
        if occupancy >= road.capacity:
            return travel_time * 100
        return travel_time

    def _road_state(self, road: Road, occupancy: int) -> dict[str, str | float | int]:
        """Provide one road's capacity and congestion data for the dashboard."""
        return {
            "id": road.id,
            "occupancy": occupancy,
            "capacity": road.capacity,
            "densityRatio": round(density_ratio(road, occupancy), 3),
            "currentTravelTimeSeconds": round(
                congested_travel_time_seconds(road, occupancy), 2
            ),
        }

    def _metrics(self, occupancies: Counter[str]) -> dict[str, float | int]:
        """Calculate project metrics from the current state without storing duplicates."""
        vehicles = tuple(self.vehicles.values())
        completed = tuple(
            vehicle for vehicle in vehicles if vehicle.status is VehicleStatus.COMPLETED
        )
        total_waiting_time = sum(vehicle.waiting_time_seconds for vehicle in vehicles)
        total_travel_time = sum(vehicle.travel_time_seconds for vehicle in vehicles)
        densities = [density_ratio(road, occupancies[road.id]) for road in self.network.roads]
        queue_lengths = self._queue_lengths().values()

        return {
            "totalVehicles": len(vehicles),
            "completedVehicles": len(completed),
            "totalWaitingTimeSeconds": round(total_waiting_time, 2),
            "averageWaitingTimeSeconds": round(
                total_waiting_time / len(vehicles), 2
            )
            if vehicles
            else 0.0,
            "totalTravelTimeSeconds": round(total_travel_time, 2),
            "averageCompletedTravelTimeSeconds": round(
                sum(vehicle.travel_time_seconds for vehicle in completed) / len(completed), 2
            )
            if completed
            else 0.0,
            "averageRoadDensity": round(sum(densities) / len(densities), 3)
            if densities
            else 0.0,
            "maximumRoadDensity": round(max(densities), 3) if densities else 0.0,
            "maximumQueueLength": max(queue_lengths, default=0),
        }

    def _current_road(self, vehicle: Vehicle) -> Road:
        """Look up the road occupied by a non-completed vehicle."""
        current_road_id = vehicle.current_road_id
        if current_road_id is None:
            raise NetworkValidationError(
                f"Completed vehicle '{vehicle.id}' does not occupy a road."
            )
        return self.network.get_road(current_road_id)
