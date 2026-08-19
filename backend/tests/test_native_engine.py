"""Tests for native simulation-engine capability reporting."""

import unittest
from unittest.mock import patch

from app.native_engine import advance_native_clock, advance_native_state, compare_native_state, compare_tick_elapsed, native_core_status, serialize_simulation_state, shadow_validate_tick, validate_native_state_update


class NativeEngineStatusTests(unittest.TestCase):
    """Keep native capability reporting safe when the DLL is unavailable."""

    @patch("app.native_engine._NATIVE_DLL_PATHS", ())
    def test_status_reports_python_fallback(self) -> None:
        """Make the active simulation implementation explicit to operators."""
        status = native_core_status()
        self.assertFalse(status["available"])
        self.assertEqual(status["simulationEngine"], "python-fallback")
        self.assertEqual(status["nativeMode"], "unavailable")

    @patch("app.native_engine._NATIVE_DLL_PATHS", ())
    def test_tick_contract_falls_back_when_native_core_is_unavailable(self) -> None:
        """Keep callers safe until a compatible 64-bit native build exists."""
        result = advance_native_clock("CITYPULSE_STATE1\nT|0", 1)
        self.assertIsNone(result)

    def test_state_serialization_includes_vehicle_and_signal_records(self) -> None:
        """Keep the native payload aligned with the dashboard simulation snapshot."""
        payload = serialize_simulation_state(
            {
                "elapsedSeconds": 4,
                "vehicles": [{"id": "car-1", "status": "moving", "currentRoadId": "R1", "positionMeters": 12, "isEmergency": True}],
                "signals": [{"intersectionId": "I1", "phase": "north_south", "remainingSeconds": 3}],
            }
        )
        self.assertIn("T|4", payload)
        self.assertIn("V|car-1|moving|R1|12|1", payload)
        self.assertIn("S|I1|north_south|3", payload)

    @patch("app.native_engine._NATIVE_DLL_PATHS", ())
    def test_state_tick_falls_back_when_native_core_is_unavailable(self) -> None:
        """Keep state updates safe until a compatible native DLL is installed."""
        self.assertIsNone(advance_native_state("CITYPULSE_STATE1\nT|0", 1))

    @patch("app.native_engine.advance_native_clock", return_value=None)
    def test_consistency_check_rejects_unavailable_native_result(self, _native_clock) -> None:
        """Prevent native state from becoming authoritative without a comparison."""
        self.assertFalse(compare_tick_elapsed("CITYPULSE_STATE1\nT|0", 1, 0))

    def test_state_validation_requires_all_records_to_survive(self) -> None:
        """Reject native output that drops a vehicle or signal record."""
        original = "CITYPULSE_STATE1\nT|0\nV|car-1|moving|R1|0\nS|I1|north_south|3"
        updated = "CITYPULSE_STATE1\nT|1\nV|car-1|moving|R1|1\nS|I1|north_south|2"
        self.assertTrue(validate_native_state_update(original, updated, 1))
        self.assertFalse(validate_native_state_update(original, "CITYPULSE_STATE1\nT|1", 1))

    def test_signal_state_is_part_of_the_native_contract(self) -> None:
        """Keep signal phase and countdown records required for native ticks."""
        payload = serialize_simulation_state(
            {"elapsedSeconds": 0, "vehicles": [], "signals": [{"intersectionId": "I1", "phase": "north_south", "remainingSeconds": 10}]}
        )
        self.assertIn("S|I1|north_south|10", payload)

    def test_queue_lengths_are_part_of_the_native_contract(self) -> None:
        """Expose road queues so native capacity rules can be compared later."""
        payload = serialize_simulation_state(
            {"elapsedSeconds": 0, "vehicles": [], "signals": [], "queueLengths": {"R1": 2}}
        )
        self.assertIn("Q|R1|2", payload)

    def test_congestion_records_are_part_of_the_native_contract(self) -> None:
        """Expose density and travel-time penalties for native optimization."""
        payload = serialize_simulation_state(
            {"elapsedSeconds": 0, "vehicles": [], "signals": [], "roads": [{"id": "R1", "densityRatio": 0.5, "travelTimeSeconds": 12}]}
        )
        self.assertIn("C|R1|0.5|12", payload)

    def test_accident_closures_are_part_of_the_native_contract(self) -> None:
        """Expose closed roads so native rerouting can avoid accidents."""
        payload = serialize_simulation_state(
            {"elapsedSeconds": 0, "vehicles": [], "signals": [], "closedRoads": ["R1"]}
        )
        self.assertIn("A|R1|closed", payload)

    def test_complete_native_comparison_accepts_preserved_state_records(self) -> None:
        """Accept a native result only when every contract record remains present."""
        snapshot = {
            "elapsedSeconds": 0,
            "vehicles": [{"id": "car-1", "status": "moving", "currentRoadId": "R1", "positionMeters": 0, "isEmergency": True}],
            "signals": [{"intersectionId": "I1", "phase": "north_south", "remainingSeconds": 3}],
            "queueLengths": {"R1": 1},
            "roads": [{"id": "R1", "densityRatio": 0.2, "travelTimeSeconds": 10}],
            "closedRoads": ["R2"],
        }
        updated = serialize_simulation_state({**snapshot, "elapsedSeconds": 1})
        self.assertTrue(compare_native_state(snapshot, updated, 1))

    @patch("app.native_engine.advance_native_state", return_value=None)
    def test_shadow_tick_is_safe_when_native_engine_is_unavailable(self, _advance) -> None:
        """Keep API ticks successful while the optional native engine is absent."""
        self.assertFalse(shadow_validate_tick({"elapsedSeconds": 0, "vehicles": [], "signals": []}, 1))


if __name__ == "__main__":
    unittest.main()
