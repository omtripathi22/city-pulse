"""Capability boundary for the native C++ simulation engine.

I keep this module deliberately small while the native engine is migrated in
safe stages. The Python simulator remains authoritative until a native tick
implementation can reproduce its signal, queue, accident, and emergency rules.
"""

from __future__ import annotations

from ctypes import CDLL, c_char_p, c_int
from typing import Any

from app.native_bridge import _NATIVE_DLL_PATHS


def native_core_status() -> dict[str, str | bool]:
    """Report whether a loadable native core is available to the API."""
    for dll_path in _NATIVE_DLL_PATHS:
        if not dll_path.exists():
            continue
        try:
            dll = CDLL(str(dll_path))
            version_function = dll.citypulse_core_version
            version_function.argtypes = []
            version_function.restype = c_char_p
            raw_version = version_function()
            return {
                "available": True,
                "version": raw_version.decode("utf-8") if raw_version else "unknown",
                "simulationEngine": "python-fallback",
                "nativeMode": "shadow-validation",
            }
        except (AttributeError, OSError):
            continue
    return {
        "available": False,
        "version": "unavailable",
        "simulationEngine": "python-fallback",
        "nativeMode": "unavailable",
    }


def advance_native_clock(serialized_state: str, seconds: int) -> float | None:
    """Advance the native state clock and return its new elapsed time."""
    for dll_path in _NATIVE_DLL_PATHS:
        if not dll_path.exists():
            continue
        try:
            dll = CDLL(str(dll_path))
            tick = dll.citypulse_simulation_tick
            tick.argtypes = [c_char_p, c_int]
            tick.restype = c_char_p
            raw_result = tick(serialized_state.encode("utf-8"), seconds)
        except (AttributeError, OSError):
            continue
        if not raw_result:
            return None
        status, *parts = raw_result.decode("utf-8").split("|", 2)
        if status != "OK" or len(parts) != 2 or parts[0] != "T":
            return None
        return float(parts[1])
    return None


def serialize_simulation_state(snapshot: dict[str, Any]) -> str:
    """Serialize elapsed time, vehicles, and signals for the native contract."""
    lines = ["CITYPULSE_STATE1", f"T|{snapshot.get('elapsedSeconds', 0)}"]
    for vehicle in snapshot.get("vehicles", []):
        lines.append(
            "V|"
            f"{vehicle.get('id', '')}|{vehicle.get('status', '')}|"
            f"{vehicle.get('currentRoadId') or ''}|{vehicle.get('positionMeters', 0)}|"
            f"{1 if vehicle.get('isEmergency', False) else 0}"
        )
    for signal in snapshot.get("signals", []):
        lines.append(
            "S|"
            f"{signal.get('intersectionId', '')}|{signal.get('phase', '')}|"
            f"{signal.get('remainingSeconds', 0)}"
        )
    for road_id, queue_length in snapshot.get("queueLengths", {}).items():
        lines.append(f"Q|{road_id}|{queue_length}")
    for road in snapshot.get("roads", []):
        lines.append(
            f"C|{road.get('id', '')}|{road.get('densityRatio', 0)}|"
            f"{road.get('travelTimeSeconds', 0)}"
        )
    for road_id in snapshot.get("closedRoads", []):
        lines.append(f"A|{road_id}|closed")
    return "\n".join(lines)


def advance_native_state(serialized_state: str, seconds: int) -> str | None:
    """Advance vehicle positions and signal countdowns in the native contract."""
    for dll_path in _NATIVE_DLL_PATHS:
        if not dll_path.exists():
            continue
        try:
            dll = CDLL(str(dll_path))
            tick = dll.citypulse_simulation_tick_state
            tick.argtypes = [c_char_p, c_int]
            tick.restype = c_char_p
            raw_result = tick(serialized_state.encode("utf-8"), seconds)
        except (AttributeError, OSError):
            continue
        if not raw_result:
            return None
        result = raw_result.decode("utf-8")
        if not result.startswith("OK|STATE|"):
            return None
        return result.split("|", 2)[2]
    return None


def compare_tick_elapsed(serialized_state: str, seconds: int, python_elapsed: float) -> bool:
    """Check that native elapsed time agrees with the Python simulation clock."""
    native_elapsed = advance_native_clock(serialized_state, seconds)
    if native_elapsed is None:
        return False
    return abs(native_elapsed - (python_elapsed + seconds)) < 1e-9


def validate_native_state_update(serialized_state: str, updated_state: str, seconds: int) -> bool:
    """Validate the native tick header, elapsed time, and record identity."""
    original_lines = serialized_state.splitlines()
    updated_lines = updated_state.splitlines()
    if not original_lines or not updated_lines or updated_lines[0] != "CITYPULSE_STATE1":
        return False
    original_records = [
        line.split("|", 2)[:2] for line in original_lines[1:] if line and not line.startswith("T|")
    ]
    updated_records = [
        line.split("|", 2)[:2] for line in updated_lines[1:] if line and not line.startswith("T|")
    ]
    if {tuple(record) for record in original_records} != {
        tuple(record) for record in updated_records
    }:
        return False
    elapsed = next((line for line in updated_lines if line.startswith("T|")), "")
    original_elapsed = next((line for line in original_lines if line.startswith("T|")), "")
    if not elapsed or not original_elapsed:
        return False
    return float(elapsed.split("|", 1)[1]) >= float(original_elapsed.split("|", 1)[1]) + seconds


def shadow_validate_tick(snapshot: dict[str, Any], seconds: int) -> bool:
    """Compare a native shadow tick without changing the live Python response."""
    serialized = serialize_simulation_state(snapshot)
    updated = advance_native_state(serialized, seconds)
    return updated is not None and validate_native_state_update(serialized, updated, seconds)


def compare_native_state(snapshot: dict[str, Any], updated_state: str, seconds: int) -> bool:
    """Run the complete structural comparison for a native state update."""
    original = serialize_simulation_state(snapshot)
    return validate_native_state_update(original, updated_state, seconds)
