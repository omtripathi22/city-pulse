# Traffic Flow Optimization System

A graph-based city traffic simulator that will model road congestion, route vehicles with Dijkstra's algorithm, and compare fixed and adaptive traffic-signal strategies.

## Project layout

```text
backend/   FastAPI service and traffic-simulation engine
frontend/  React dashboard for the road-network visualization
```

## Current status

Steps 1–8 are complete: the project now has a validated city graph, Dijkstra
routing, fixed and queue-adaptive traffic signals, capacity-limited queues,
congestion-aware route costs, emergency priority, accident closures, metrics,
and a live React dashboard with a Canvas city map.

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
- Add `&emergency=true` to give that vehicle signal priority when it queues.
- `POST /simulation/step?seconds=30` advances all lights and vehicles.
- `GET /simulation/state` returns the current vehicle positions and signal states.
- `POST /simulation/accidents?road_id=R01` closes a road and reroutes affected trips.
- `DELETE /simulation/accidents/R01` reopens a closed road.

For example, reset the simulation, add a vehicle, then step 30 seconds. The
state response will show its current road, distance along that road, time spent
travelling, time spent waiting, and every signal's active phase.

Each simulation state now also includes road occupancy, capacity, density,
congestion-adjusted travel time, queue lengths, and headline metrics. These
include total and average waiting time, completed trips, total travel time,
maximum queue length, and average/maximum road density.

## Congestion model

The simulation uses a BPR-style cost curve:

```text
current travel time = free-flow time × (1 + 0.15 × density⁴)
```

Density is `road occupancy / road capacity`. New vehicles use these current
costs when Dijkstra chooses their route. A vehicle at an intersection must also
wait when its next road is at capacity, even if its signal is green.

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
The live dashboard will be available at `http://localhost:5173`.

## Dashboard controls

The dashboard draws all roads, intersections, live signal phases, moving cars,
and road density. It connects directly to the local FastAPI service.

1. Select a source and destination, then choose **Add vehicle**.
2. Use **Step 1s** or **Step 10s** to advance a controlled amount of time.
3. Use **Run live** to advance the simulation continuously, then **Pause live run**.
4. Use **Reset simulation** to return to an empty map and initial signal phases.

The lower congestion panel ranks the five most occupied roads. The four metric
cards show simulation time, completed trips, average wait, and the largest queue.

## Signal strategies

The dashboard's **Signal strategy** control resets the live scenario to keep
strategy runs comparable:

- **Fixed cycle** gives horizontal and vertical approaches the same preset green
  and yellow timing.
- **Adaptive queues** uses a greedy rule: after a minimum green period, it moves
  toward the approach with the larger waiting queue. It still applies a maximum
  green period to prevent one direction from being ignored indefinitely.

Choose **Compare strategies** to run the same eight-vehicle demand through both
policies for 180 simulated seconds. It does not affect your live scenario and
reports completed trips, average wait, and peak queue for each policy.

## Emergency and accident scenarios

Enable **Emergency vehicle priority** before adding a vehicle to mark it as an
ambulance-style trip. When it reaches a red signal, the controller pre-empts the
phase for that approach on the next tick.

Use the **Accident road** selector and **Close road** to simulate a blocked
segment. Closed roads are dashed red on the map, excluded from new routes, and
active vehicles with that segment ahead of them are rerouted when an alternate
path exists. **Reopen road** restores the segment for future routing.

## Running the graph tests

```powershell
cd backend
python -B -m unittest discover -s tests -v
```
