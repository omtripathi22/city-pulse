"""Tests for fixed-time lights and the first vehicle movement rules."""

import unittest
from pathlib import Path

from app.graph import RoadNetwork
from app.models import Intersection, NetworkValidationError, Road
from app.signals import FixedTimeSignal, SignalAxis, SignalPhase, SignalStrategy
from app.simulation import TrafficSimulation, VehicleStatus, compare_signal_strategies


DATA_DIRECTORY = Path(__file__).resolve().parents[1] / "data"


def make_two_road_network() -> RoadNetwork:
    """Build a tiny straight network where one middle signal controls the trip."""
    return RoadNetwork(
        intersections=[
            Intersection(id="A", x=0, y=0),
            Intersection(id="B", x=10, y=0),
            Intersection(id="C", x=20, y=0),
        ],
        roads=[
            Road(
                id="AB",
                source_id="A",
                destination_id="B",
                length_meters=10,
                speed_limit_kmph=36,
                lanes=1,
                capacity=10,
            ),
            Road(
                id="BC",
                source_id="B",
                destination_id="C",
                length_meters=10,
                speed_limit_kmph=36,
                lanes=1,
                capacity=10,
            ),
        ],
    )


def make_capacity_network() -> RoadNetwork:
    """Build a short route where the second road can hold only one vehicle."""
    return RoadNetwork(
        intersections=[
            Intersection(id="A", x=0, y=0),
            Intersection(id="B", x=10, y=0),
            Intersection(id="C", x=20, y=0),
        ],
        roads=[
            Road(
                id="AB",
                source_id="A",
                destination_id="B",
                length_meters=10,
                speed_limit_kmph=36,
                lanes=1,
                capacity=2,
            ),
            Road(
                id="BC",
                source_id="B",
                destination_id="C",
                length_meters=10,
                speed_limit_kmph=36,
                lanes=1,
                capacity=1,
            ),
        ],
    )


def make_accident_network() -> RoadNetwork:
    """Build a primary route plus a longer reverse-direction detour around one road."""
    intersections = [
        Intersection(id="A", x=0, y=0),
        Intersection(id="B", x=10, y=0),
        Intersection(id="D", x=0, y=10),
        Intersection(id="E", x=10, y=10),
        Intersection(id="C", x=20, y=10),
    ]
    roads = [
        Road("AB", "A", "B", 10, 36, 1, 10),
        Road("BE", "B", "E", 10, 36, 1, 10),
        Road("EC", "E", "C", 10, 36, 1, 10),
        Road("BA", "B", "A", 10, 36, 1, 10),
        Road("AD", "A", "D", 10, 36, 1, 10),
        Road("DE", "D", "E", 10, 36, 1, 10),
    ]
    return RoadNetwork(intersections=intersections, roads=roads)


class FixedTimeSignalTests(unittest.TestCase):
    """Prove the fixed cycle changes through green and yellow in the right order."""

    def test_signal_rotates_between_all_four_phases(self) -> None:
        """Keep the phase order predictable before adaptive control is introduced."""
        signal = FixedTimeSignal("B", green_seconds=2, yellow_seconds=1)

        signal.advance(2)
        self.assertEqual(signal.phase, SignalPhase.HORIZONTAL_YELLOW)
        signal.advance(1)
        self.assertEqual(signal.phase, SignalPhase.VERTICAL_GREEN)
        signal.advance(2)
        self.assertEqual(signal.phase, SignalPhase.VERTICAL_YELLOW)
        signal.advance(1)
        self.assertEqual(signal.phase, SignalPhase.HORIZONTAL_GREEN)

    def test_adaptive_signal_serves_the_larger_waiting_queue(self) -> None:
        """Switch to the queued vertical approach once the minimum green has elapsed."""
        signal = FixedTimeSignal(
            "B",
            strategy=SignalStrategy.ADAPTIVE,
            minimum_green_seconds=2,
            maximum_green_seconds=5,
            yellow_seconds=1,
        )
        vertical_demand = {
            SignalAxis.HORIZONTAL: 0,
            SignalAxis.VERTICAL: 3,
        }

        signal.advance(1, vertical_demand)
        self.assertEqual(signal.phase, SignalPhase.HORIZONTAL_GREEN)
        signal.advance(1, vertical_demand)
        self.assertEqual(signal.phase, SignalPhase.HORIZONTAL_YELLOW)
        signal.advance(1, vertical_demand)
        self.assertEqual(signal.phase, SignalPhase.VERTICAL_GREEN)

class TrafficSimulationTests(unittest.TestCase):
    """Check that vehicles respect the current signal state as they move."""

    def setUp(self) -> None:
        """Create a new short road network for each independent simulation test."""
        self.network = make_two_road_network()

    def test_emergency_priority_preempts_a_red_approach(self) -> None:
        """Give an emergency car a green signal on the tick after it reaches the queue."""
        simulation = TrafficSimulation(
            self.network,
            signals={
                "B": FixedTimeSignal(
                    "B",
                    green_seconds=10,
                    yellow_seconds=2,
                    phase=SignalPhase.VERTICAL_GREEN,
                )
            },
        )
        vehicle = simulation.add_vehicle("ambulance-1", "A", "C", is_emergency=True)

        simulation.advance(1)
        self.assertEqual(vehicle.status, VehicleStatus.WAITING)
        self.assertTrue(vehicle.is_emergency)

        simulation.advance(1)
        self.assertEqual(vehicle.status, VehicleStatus.MOVING)
        self.assertEqual(vehicle.current_road_id, "BC")

    def test_vehicle_waits_at_yellow_then_moves_when_green_returns(self) -> None:
        """Make a vehicle stop at the middle light before it can enter the next road."""
        simulation = TrafficSimulation(
            self.network,
            signals={"B": FixedTimeSignal("B", green_seconds=1, yellow_seconds=1)},
        )
        vehicle = simulation.add_vehicle("car-1", "A", "C")

        simulation.advance(1)
        self.assertEqual(vehicle.status, VehicleStatus.WAITING)
        self.assertEqual(vehicle.waiting_time_seconds, 1)

        simulation.advance(3)
        self.assertEqual(vehicle.status, VehicleStatus.MOVING)
        self.assertEqual(vehicle.current_road_id, "BC")
        self.assertEqual(vehicle.waiting_time_seconds, 3)

        simulation.advance(1)
        self.assertEqual(vehicle.status, VehicleStatus.COMPLETED)

    def test_same_source_and_destination_is_complete_immediately(self) -> None:
        """Avoid creating an invalid current-road state for a zero-distance trip."""
        simulation = TrafficSimulation(self.network)
        vehicle = simulation.add_vehicle("car-1", "A", "A")

        self.assertEqual(vehicle.status, VehicleStatus.COMPLETED)
        self.assertIsNone(vehicle.current_road_id)

    def test_snapshot_reports_vehicle_counts_and_signal_states(self) -> None:
        """Give the future dashboard a self-contained, serializable simulation view."""
        simulation = TrafficSimulation(self.network)
        simulation.add_vehicle("car-1", "A", "C")

        snapshot = simulation.snapshot()

        self.assertEqual(snapshot["elapsedSeconds"], 0)
        self.assertEqual(snapshot["vehicleCounts"], {
            "moving": 1,
            "waiting": 0,
            "completed": 0,
        })
        self.assertEqual(len(snapshot["signals"]), 3)

    def test_simulation_rejects_fractional_ticks(self) -> None:
        """Keep the initial engine deterministic by allowing only one-second steps."""
        simulation = TrafficSimulation(self.network)

        with self.assertRaises(NetworkValidationError):
            simulation.advance(0.5)

    def test_adaptive_strategy_is_reported_in_the_snapshot(self) -> None:
        """Expose the chosen signal policy so the dashboard can label a live run."""
        simulation = TrafficSimulation(
            self.network,
            signal_strategy=SignalStrategy.ADAPTIVE,
        )

        self.assertEqual(simulation.snapshot()["signalStrategy"], "adaptive")

    def test_full_downstream_road_creates_a_capacity_queue(self) -> None:
        """Hold a car at green when its next road is full, then release it safely."""
        simulation = TrafficSimulation(make_capacity_network())
        first_vehicle = simulation.add_vehicle("car-1", "A", "C")
        second_vehicle = simulation.add_vehicle("car-2", "A", "C")

        simulation.advance(1)

        self.assertEqual(first_vehicle.current_road_id, "BC")
        self.assertEqual(second_vehicle.status, VehicleStatus.WAITING)
        self.assertEqual(second_vehicle.waiting_reason.value, "road_capacity")
        self.assertEqual(simulation.snapshot()["queueLengths"], {"AB": 1})
        self.assertEqual(simulation.snapshot()["metrics"]["maximumQueueLength"], 1)

        simulation.advance(1)

        self.assertEqual(first_vehicle.status, VehicleStatus.COMPLETED)
        self.assertEqual(second_vehicle.status, VehicleStatus.MOVING)
        self.assertEqual(second_vehicle.current_road_id, "BC")
        self.assertEqual(simulation.snapshot()["metrics"]["maximumQueueLength"], 1)

    def test_comparison_runs_both_strategies_without_a_live_simulation(self) -> None:
        """Return comparable metrics for equal traffic demand under both policies."""
        network = RoadNetwork.from_json_file(DATA_DIRECTORY / "city-map.json")

        comparison = compare_signal_strategies(network, seconds=30)

        self.assertEqual(comparison["durationSeconds"], 30)
        self.assertEqual(comparison["vehicleCount"], 8)
        self.assertEqual(set(comparison["results"]), {"fixed", "adaptive"})

    def test_accident_closes_a_future_road_and_reroutes_active_vehicle(self) -> None:
        """Move an active trip onto a detour when its planned road is closed."""
        network = make_accident_network()
        simulation = TrafficSimulation(network)
        vehicle = simulation.add_vehicle("car-1", "A", "C")

        simulation.close_road("BE")

        self.assertIn("BE", simulation.closed_roads)
        self.assertNotIn("BE", vehicle.route.road_ids[vehicle.current_road_index + 1 :])

        simulation.advance(1)
        self.assertEqual(vehicle.current_road_id, "BA")
        self.assertNotEqual(vehicle.waiting_reason, "accident")

        simulation.reopen_road("BE")
        self.assertNotIn("BE", simulation.closed_roads)


if __name__ == "__main__":
    unittest.main()
