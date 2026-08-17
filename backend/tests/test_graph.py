"""Tests for the city graph before route-finding is introduced."""

from pathlib import Path
import unittest

from app.graph import RoadNetwork
from app.models import Intersection, NetworkValidationError, Road
from app.routing import RouteNotFoundError, find_shortest_route


DATA_DIRECTORY = Path(__file__).resolve().parents[1] / "data"


class RoadNetworkTests(unittest.TestCase):
    """Check that I can load and query the starter road network safely."""

    def setUp(self) -> None:
        """Load a fresh copy of the sample map for each independent test."""
        self.network = RoadNetwork.from_json_file(DATA_DIRECTORY / "city-map.json")

    def test_starter_map_has_expected_size(self) -> None:
        """Keep the intentionally small 3x3 grid stable while I build the MVP."""
        self.assertEqual(self.network.intersection_count, 9)
        self.assertEqual(self.network.road_count, 24)

    def test_outgoing_roads_are_directed(self) -> None:
        """Confirm the graph returns only roads a vehicle may actually leave on."""
        road_ids = {road.id for road in self.network.outgoing_roads("I5")}
        self.assertEqual(road_ids, {"R06", "R07", "R16", "R21"})

    def test_unknown_intersection_is_rejected(self) -> None:
        """Return a useful validation error instead of silently hiding map mistakes."""
        with self.assertRaises(NetworkValidationError):
            self.network.outgoing_roads("missing")

    def test_base_travel_time_uses_road_speed(self) -> None:
        """Verify the free-flow cost that Dijkstra will consume in the next step."""
        road = Road(
            id="test-road",
            source_id="I1",
            destination_id="I2",
            length_meters=100,
            speed_limit_kmph=36,
            lanes=1,
            capacity=10,
        )
        self.assertEqual(road.base_travel_time_seconds, 10)


class DijkstraRoutingTests(unittest.TestCase):
    """Check the routing rules before vehicles begin consuming the routes."""

    def setUp(self) -> None:
        """Load the same stable map that the API serves to the dashboard."""
        self.network = RoadNetwork.from_json_file(DATA_DIRECTORY / "city-map.json")

    def test_finds_the_fastest_route_across_the_grid(self) -> None:
        """Choose the minimum free-flow travel-time path, not simply the fewest roads."""
        route = find_shortest_route(self.network, "I1", "I9")

        self.assertEqual(route.road_ids, ("R13", "R19", "R09", "R11"))
        self.assertEqual(route.intersection_ids, ("I1", "I4", "I7", "I8", "I9"))
        self.assertAlmostEqual(route.total_travel_time_seconds, 96.43, places=2)

    def test_same_origin_and_destination_returns_an_empty_route(self) -> None:
        """Avoid doing unnecessary graph work when a trip starts at its destination."""
        route = find_shortest_route(self.network, "I5", "I5")

        self.assertEqual(route.road_ids, ())
        self.assertEqual(route.intersection_ids, ("I5",))
        self.assertEqual(route.total_travel_time_seconds, 0)

    def test_missing_directed_path_raises_a_useful_error(self) -> None:
        """Tell callers when a valid intersection is isolated from the destination."""
        disconnected_network = RoadNetwork(
            intersections=[
                Intersection(id="A", x=0, y=0),
                Intersection(id="B", x=100, y=0),
            ],
            roads=[],
        )

        with self.assertRaises(RouteNotFoundError):
            find_shortest_route(disconnected_network, "A", "B")

    def test_custom_cost_can_model_a_future_congestion_penalty(self) -> None:
        """Keep the router ready to switch paths when a road becomes congested."""
        route = find_shortest_route(
            self.network,
            "I1",
            "I9",
            road_cost=lambda road: 1_000 if road.id == "R03" else road.base_travel_time_seconds,
        )

        self.assertNotIn("R03", route.road_ids)


if __name__ == "__main__":
    unittest.main()
