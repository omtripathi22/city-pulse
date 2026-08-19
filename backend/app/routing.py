"""Shortest-path routing for vehicles travelling through the city graph."""

from __future__ import annotations

import heapq
from collections.abc import Callable
from dataclasses import dataclass

from app.graph import RoadNetwork
from app.models import NetworkValidationError, Road
from app.native_bridge import find_shortest_route_native


class RouteNotFoundError(NetworkValidationError):
    """Explain that two valid intersections have no directed route between them."""


@dataclass(frozen=True, slots=True)
class Route:
    """Describe the directed roads and intersections a vehicle should follow.

    I retain both representations because the simulator moves along road ids,
    while the dashboard can display the simpler intersection-by-intersection path.
    """

    source_id: str
    destination_id: str
    road_ids: tuple[str, ...]
    intersection_ids: tuple[str, ...]
    total_travel_time_seconds: float

    def as_dict(self) -> dict[str, str | float | list[str]]:
        """Return a JSON-friendly response without leaking internal graph objects."""
        return {
            "source": self.source_id,
            "destination": self.destination_id,
            "roadIds": list(self.road_ids),
            "intersectionIds": list(self.intersection_ids),
            "totalTravelTimeSeconds": round(self.total_travel_time_seconds, 2),
        }


RoadCostFunction = Callable[[Road], float]


def find_shortest_route(
    network: RoadNetwork,
    source_id: str,
    destination_id: str,
    road_cost: RoadCostFunction | None = None,
) -> Route:
    """Find the cheapest directed route with Dijkstra's priority-queue algorithm.

    I use free-flow travel time by default. The optional cost function lets the
    simulation later add congestion penalties without rewriting the algorithm.
    """
    network.get_intersection(source_id)
    network.get_intersection(destination_id)

    if source_id == destination_id:
        return Route(
            source_id=source_id,
            destination_id=destination_id,
            road_ids=(),
            intersection_ids=(source_id,),
            total_travel_time_seconds=0.0,
        )

    if road_cost is None:
        native_route = find_shortest_route_native(network, source_id, destination_id)
        if native_route is not None:
            return native_route

    calculate_cost = road_cost or _free_flow_cost
    distances: dict[str, float] = {source_id: 0.0}
    previous_roads: dict[str, Road] = {}
    queue: list[tuple[float, str]] = [(0.0, source_id)]

    while queue:
        current_cost, current_id = heapq.heappop(queue)
        if current_cost > distances[current_id]:
            continue
        if current_id == destination_id:
            return _reconstruct_route(
                source_id, destination_id, previous_roads, current_cost
            )

        for road in network.outgoing_roads(current_id):
            candidate_cost = current_cost + _validated_cost(road, calculate_cost)
            known_cost = distances.get(road.destination_id, float("inf"))
            if candidate_cost < known_cost:
                distances[road.destination_id] = candidate_cost
                previous_roads[road.destination_id] = road
                heapq.heappush(queue, (candidate_cost, road.destination_id))

    raise RouteNotFoundError(
        f"No directed route exists from '{source_id}' to '{destination_id}'."
    )


def _free_flow_cost(road: Road) -> float:
    """Use a road's uncongested travel time as the first routing cost model."""
    return road.base_travel_time_seconds


def _validated_cost(road: Road, calculate_cost: RoadCostFunction) -> float:
    """Reject invalid custom costs before they break Dijkstra's assumptions."""
    cost = calculate_cost(road)
    if cost < 0:
        raise NetworkValidationError(
            f"Road cost for '{road.id}' cannot be negative; Dijkstra requires "
            "non-negative weights."
        )
    return cost


def _reconstruct_route(
    source_id: str,
    destination_id: str,
    previous_roads: dict[str, Road],
    total_cost: float,
) -> Route:
    """Walk backwards through predecessor roads to build the route in travel order."""
    reversed_roads: list[Road] = []
    current_id = destination_id

    while current_id != source_id:
        road = previous_roads[current_id]
        reversed_roads.append(road)
        current_id = road.source_id

    ordered_roads = tuple(reversed(reversed_roads))
    return Route(
        source_id=source_id,
        destination_id=destination_id,
        road_ids=tuple(road.id for road in ordered_roads),
        intersection_ids=(source_id, *(road.destination_id for road in ordered_roads)),
        total_travel_time_seconds=total_cost,
    )
