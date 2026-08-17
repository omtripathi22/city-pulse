"""Tests for density and congestion-cost calculations."""

import unittest

from app.congestion import congested_travel_time_seconds, density_ratio
from app.models import Road


class CongestionCalculationTests(unittest.TestCase):
    """Check the cost model that guides congestion-aware routing."""

    def setUp(self) -> None:
        """Create one simple road with a ten-vehicle capacity for clear assertions."""
        self.road = Road(
            id="test-road",
            source_id="A",
            destination_id="B",
            length_meters=100,
            speed_limit_kmph=36,
            lanes=1,
            capacity=10,
        )

    def test_density_is_occupancy_divided_by_capacity(self) -> None:
        """Expose the basic density value used by the API and dashboard."""
        self.assertEqual(density_ratio(self.road, 5), 0.5)

    def test_congestion_penalty_grows_as_a_road_fills(self) -> None:
        """Ensure a full road costs more time than the same road when it is empty."""
        empty_time = congested_travel_time_seconds(self.road, 0)
        full_time = congested_travel_time_seconds(self.road, 10)

        self.assertEqual(empty_time, self.road.base_travel_time_seconds)
        self.assertGreater(full_time, empty_time)


if __name__ == "__main__":
    unittest.main()
