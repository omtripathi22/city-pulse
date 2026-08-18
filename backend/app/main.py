from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.graph import RoadNetwork
from app.models import NetworkValidationError
from app.routing import RouteNotFoundError, find_shortest_route
from app.signals import SignalStrategy
from app.simulation import TrafficSimulation, compare_signal_strategies


DATA_DIRECTORY = Path(__file__).resolve().parents[1] / "data"
CITY_MAP_PATH = DATA_DIRECTORY / "city-map.json"

# I load the starter network once because it is static until the map-editing stage.
road_network = RoadNetwork.from_json_file(CITY_MAP_PATH)
traffic_simulation = TrafficSimulation(road_network)


app = FastAPI(
    title="Traffic Flow Optimization System",
    version="0.1.0",
    description="API foundation for the traffic-flow simulation and dashboard.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Return a small status response so I can confirm the API is running."""
    return {"status": "ok", "service": "traffic-flow-api"}


@app.get("/network/summary", tags=["network"])
def network_summary() -> dict[str, int]:
    """Report the loaded map size without exposing simulation internals yet."""
    return {
        "intersections": road_network.intersection_count,
        "roads": road_network.road_count,
    }


@app.get("/network", tags=["network"])
def network_map() -> dict[str, list[dict[str, str | float | int]]]:
    """Return the complete static road graph for the browser-based map canvas."""
    return road_network.as_dict()


@app.get("/routes", tags=["routing"])
def route_between_intersections(
    source: str = Query(..., min_length=1, description="Starting intersection id."),
    destination: str = Query(..., min_length=1, description="Target intersection id."),
) -> dict[str, str | float | list[str]]:
    """Calculate a shortest free-flow route for the requested pair of junctions."""
    try:
        return find_shortest_route(road_network, source, destination).as_dict()
    except RouteNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except NetworkValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/simulation/state", tags=["simulation"])
def simulation_state() -> dict[str, object]:
    """Return the current signals, vehicles, and time without advancing the model."""
    return traffic_simulation.snapshot()


@app.post("/simulation/vehicles", status_code=201, tags=["simulation"])
def create_vehicle(
    source: str = Query(..., min_length=1, description="Starting intersection id."),
    destination: str = Query(..., min_length=1, description="Target intersection id."),
    vehicle_id: str | None = Query(
        default=None,
        min_length=1,
        description="Optional unique vehicle id; generated when omitted.",
    ),
    emergency: bool = Query(
        default=False,
        description="Give this vehicle emergency priority at signals.",
    ),
) -> dict[str, str | float | int | None]:
    """Add one vehicle with a shortest route, ready for subsequent simulation ticks."""
    try:
        new_vehicle_id = vehicle_id or _next_vehicle_id()
        return traffic_simulation.add_vehicle(
            new_vehicle_id, source, destination, is_emergency=emergency
        ).as_dict()
    except RouteNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except NetworkValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/simulation/step", tags=["simulation"])
def step_simulation(
    seconds: int = Query(
        default=1,
        ge=1,
        le=3_600,
        description="Whole seconds to simulate in this request.",
    ),
) -> dict[str, object]:
    """Advance fixed-time signals and every simulated vehicle by whole seconds."""
    try:
        traffic_simulation.advance(seconds)
        return traffic_simulation.snapshot()
    except NetworkValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/simulation/reset", tags=["simulation"])
def reset_simulation() -> dict[str, object]:
    """Clear vehicles and restore every signal to its initial fixed-time phase."""
    global traffic_simulation
    traffic_simulation = TrafficSimulation(
        road_network,
        signal_strategy=traffic_simulation.signal_strategy,
    )
    return traffic_simulation.snapshot()


@app.post("/simulation/strategy", tags=["simulation"])
def set_signal_strategy(
    strategy: SignalStrategy = Query(
        ..., description="Signal controller to use for a newly reset simulation."
    ),
) -> dict[str, object]:
    """Select a signal policy and reset state so both strategies start fairly."""
    global traffic_simulation
    traffic_simulation = TrafficSimulation(road_network, signal_strategy=strategy)
    return traffic_simulation.snapshot()


@app.post("/simulation/compare", tags=["simulation"])
def compare_strategies(
    seconds: int = Query(
        default=180,
        ge=1,
        le=3_600,
        description="Duration used for each identical comparison run.",
    ),
) -> dict[str, object]:
    """Compare fixed and adaptive signals without changing the live dashboard run."""
    return compare_signal_strategies(road_network, seconds)


@app.post("/simulation/accidents", tags=["simulation"])
def close_accident(
    road_id: str = Query(..., min_length=1, description="Road id to close."),
) -> dict[str, object]:
    """Close a road and let active vehicles reroute around the simulated accident."""
    try:
        traffic_simulation.close_road(road_id)
        return traffic_simulation.snapshot()
    except NetworkValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.delete("/simulation/accidents/{road_id}", tags=["simulation"])
def reopen_accident(road_id: str) -> dict[str, object]:
    """Reopen a road after its simulated accident has been cleared."""
    try:
        traffic_simulation.reopen_road(road_id)
        return traffic_simulation.snapshot()
    except NetworkValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def _next_vehicle_id() -> str:
    """Generate a readable id without colliding with a caller-provided vehicle id."""
    number = 1
    while f"vehicle-{number}" in traffic_simulation.vehicles:
        number += 1
    return f"vehicle-{number}"
