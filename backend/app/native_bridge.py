"""Optional bridge to a native C++ routing core.

The Python simulation stays authoritative for now, but this module lets the
project start using a C++17 engine without breaking the existing API when the
native build is unavailable.
"""

from __future__ import annotations

from ctypes import CDLL, c_char_p
from pathlib import Path
from typing import TYPE_CHECKING

from app.graph import RoadNetwork
from app.models import NetworkValidationError

if TYPE_CHECKING:
    from app.routing import Route


_NATIVE_DIRECTORY = Path(__file__).resolve().parents[1] / "native"
_NATIVE_DLL_PATHS = (
    _NATIVE_DIRECTORY / "citypulse_core.dll",
    _NATIVE_DIRECTORY / "Release" / "citypulse_core.dll",
    _NATIVE_DIRECTORY / "Debug" / "citypulse_core.dll",
)


def find_shortest_route_native(
    network: RoadNetwork, source_id: str, destination_id: str
) -> "Route | None":
    """Try to compute a shortest route via the C++ core, or fall back to Python."""
    dll = None
    for dll_path in _NATIVE_DLL_PATHS:
        if not dll_path.exists():
            continue
        try:
            dll = CDLL(str(dll_path))
            break
        except OSError:
            continue
    if dll is None:
        return None

    dll.citypulse_shortest_route.argtypes = [c_char_p, c_char_p, c_char_p]
    dll.citypulse_shortest_route.restype = c_char_p

    payload = _serialize_network(network).encode("utf-8")
    raw_result = dll.citypulse_shortest_route(
        payload, source_id.encode("utf-8"), destination_id.encode("utf-8")
    )
    if not raw_result:
        raise NetworkValidationError("The native route engine returned no result.")

    result = raw_result.decode("utf-8")
    status, *parts = result.split("|", 5)
    if status == "ERR":
        # Let Python's router produce its established RouteNotFoundError for
        # disconnected graphs while retaining native validation errors.
        if parts and parts[0] == "no route found":
            return None
        raise NetworkValidationError(parts[0] if parts else "The native route engine failed.")
    if status != "OK" or len(parts) != 5:
        raise NetworkValidationError("The native route engine returned malformed data.")

    source_id, destination_id, cost_text, road_text, intersection_text = parts
    road_ids = tuple(item for item in road_text.split(",") if item)
    intersection_ids = tuple(item for item in intersection_text.split(",") if item)
    return Route(
        source_id=source_id,
        destination_id=destination_id,
        road_ids=road_ids,
        intersection_ids=intersection_ids,
        total_travel_time_seconds=float(cost_text),
    )


def _serialize_network(network: RoadNetwork) -> str:
    """Serialize the graph into a compact line-based format for the DLL."""
    lines = ["CITYPULSE1"]
    for intersection in network.intersections:
        lines.append(f"I|{intersection.id}")
    for road in network.roads:
        lines.append(
            "R|"
            f"{road.source_id}|{road.destination_id}|{road.id}|{road.base_travel_time_seconds}"
        )
    return "\n".join(lines)
