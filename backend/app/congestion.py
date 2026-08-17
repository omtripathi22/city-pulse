"""Road-density calculations used by routing and simulation snapshots."""

from __future__ import annotations

from app.models import NetworkValidationError, Road


CONGESTION_ALPHA = 0.15
CONGESTION_BETA = 4


def density_ratio(road: Road, occupancy: int) -> float:
    """Return the share of a road's vehicle capacity currently in use.

    I allow ratios above one in the calculation so a corrupted state is visible
    in diagnostics, although the simulator itself prevents that from happening.
    """
    if occupancy < 0:
        raise NetworkValidationError("Road occupancy cannot be negative.")
    return occupancy / road.capacity


def congested_travel_time_seconds(road: Road, occupancy: int) -> float:
    """Apply a BPR-style congestion penalty to the road's free-flow travel time.

    The Bureau of Public Roads curve gives a gentle penalty at low density and a
    much stronger one near capacity. It is deterministic and easy to explain in
    this first optimization project.
    """
    ratio = density_ratio(road, occupancy)
    multiplier = 1 + CONGESTION_ALPHA * ratio**CONGESTION_BETA
    return road.base_travel_time_seconds * multiplier
