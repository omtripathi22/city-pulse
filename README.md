# Traffic Flow Optimization System

A graph-based city traffic simulator that will model road congestion, route vehicles with Dijkstra's algorithm, and compare fixed and adaptive traffic-signal strategies.

## Project layout

```text
backend/   FastAPI service and traffic-simulation engine
frontend/  React dashboard for the road-network visualization
```

## Current status

Steps 1–4 are complete: the project now has a validated city graph, Dijkstra
routing, fixed-time traffic signals, and a one-second vehicle simulation loop.
Congestion queues and the visual dashboard are the next major additions.

## Starter city map

The map lives in `backend/data/city-map.json`. It contains nine intersections
and 24 directed roads: every two-way street is represented by two separate road
records. A road stores length, speed limit, lane count, and capacity so later
stages can calculate both free-flow travel time and congestion penalties.

## Routing API

`GET /routes?source=I1&destination=I9` returns the least-cost route using
Dijkstra's algorithm and each road's free-flow travel time. The router also
accepts a custom cost function internally, which is how a later simulation
stage will account for live congestion without changing the core algorithm.

## Simulation API

The starter engine exposes these controls in FastAPI's `/docs` page:

- `POST /simulation/reset` clears all vehicles and restores signal cycles.
- `POST /simulation/vehicles?source=I1&destination=I9` adds a vehicle.
- `POST /simulation/step?seconds=30` advances all lights and vehicles.
- `GET /simulation/state` returns the current vehicle positions and signal states.

For example, reset the simulation, add a vehicle, then step 30 seconds. The
state response will show its current road, distance along that road, time spent
travelling, time spent waiting, and every signal's active phase.

## Planned build stages

1. Project foundation
2. City graph and sample road network
3. Dijkstra routing and tests
4. Vehicles and fixed-time signals
5. Congestion, queues, and metrics
6. Live dashboard visualization
7. Adaptive signal optimization

## Running the starter applications

Install the dependencies after they are added locally:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

In a separate terminal:

```powershell
cd frontend
npm install
npm run dev
```

The backend health endpoint will be available at `http://localhost:8000/health`.

## Running the graph tests

```powershell
cd backend
python -B -m unittest discover -s tests -v
```
