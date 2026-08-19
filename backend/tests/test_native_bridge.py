"""Tests for the optional native routing bridge and its safe fallback behavior."""

from pathlib import Path
import unittest
from unittest.mock import patch

from app.graph import RoadNetwork
from app.native_bridge import find_shortest_route_native
from app.routing import find_shortest_route


DATA_DIRECTORY = Path(__file__).resolve().parents[1] / "data"


class NativeBridgeTests(unittest.TestCase):
    """Verify native routing remains compatible with the Python route contract."""

    def setUp(self) -> None:
        """Load the same map used by the API tests."""
        self.network = RoadNetwork.from_json_file(DATA_DIRECTORY / "city-map.json")

    @patch("app.routing.find_shortest_route_native")
    def test_standard_routes_prefer_native_engine(self, native_route) -> None:
        """Use a native route whenever the optional engine provides one."""
        native_route.return_value = find_shortest_route(
            self.network, "I1", "I9", road_cost=lambda road: road.base_travel_time_seconds
        )

        route = find_shortest_route(self.network, "I1", "I9")

        native_route.assert_called_once_with(self.network, "I1", "I9")
        self.assertEqual(route.destination_id, "I9")

    @patch("app.native_bridge.CDLL", side_effect=OSError("wrong architecture"))
    def test_unloadable_dll_returns_none_for_python_fallback(self, _load_library) -> None:
        """Treat an incompatible DLL as unavailable instead of breaking the API."""
        result = find_shortest_route_native(self.network, "I1", "I9")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
