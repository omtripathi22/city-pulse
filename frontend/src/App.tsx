import { useCallback, useEffect, useRef, useState } from 'react'
import {
  addVehicle,
  closeAccident,
  compareStrategies,
  getNetwork,
  getSimulationState,
  resetSimulation,
  reopenAccident,
  setSignalStrategy,
  stepSimulation,
} from './api'
import TrafficCanvas from './TrafficCanvas'
import type { NetworkMap, SignalStrategy, SimulationState, StrategyComparison } from './types'

function formatSeconds(seconds: number): string {
  const rounded = Math.round(seconds)
  const minutes = Math.floor(rounded / 60)
  const remainder = rounded % 60
  return minutes ? `${minutes}m ${remainder}s` : `${remainder}s`
}

function App() {
  const [network, setNetwork] = useState<NetworkMap | null>(null)
  const [simulation, setSimulation] = useState<SimulationState | null>(null)
  const [source, setSource] = useState('I1')
  const [destination, setDestination] = useState('I9')
  const [emergency, setEmergency] = useState(false)
  const [accidentRoadId, setAccidentRoadId] = useState('R01')
  const [comparison, setComparison] = useState<StrategyComparison | null>(null)
  const [isRunning, setIsRunning] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const requestInFlight = useRef(false)

  const refresh = useCallback(async () => {
    const [nextNetwork, nextSimulation] = await Promise.all([
      getNetwork(),
      getSimulationState(),
    ])
    setNetwork(nextNetwork)
    setSimulation(nextSimulation)
    setSource((current) => current || nextNetwork.intersections[0]?.id || '')
    setDestination(
      (current) => current || nextNetwork.intersections[nextNetwork.intersections.length - 1]?.id || '',
    )
  }, [])

  useEffect(() => {
    void refresh().catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : 'Could not reach the API.')
    })
  }, [refresh])

  const advance = useCallback(async (seconds: number) => {
    if (requestInFlight.current) return
    requestInFlight.current = true
    try {
      setIsProcessing(true)
      setSimulation(await stepSimulation(seconds))
      setError(null)
    } catch (reason) {
      setIsRunning(false)
      setError(reason instanceof Error ? reason.message : 'The simulation could not advance.')
    } finally {
      requestInFlight.current = false
      setIsProcessing(false)
    }
  }, [])

  useEffect(() => {
    if (!isRunning) return undefined
    const interval = window.setInterval(() => void advance(1), 700)
    return () => window.clearInterval(interval)
  }, [advance, isRunning])

  async function handleAddVehicle(): Promise<void> {
    if (!source || !destination || source === destination) {
      setError('Choose two different intersections for a vehicle trip.')
      return
    }
    try {
      setIsProcessing(true)
      await addVehicle(source, destination, emergency)
      setSimulation(await getSimulationState())
      setError(null)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The vehicle could not be added.')
    } finally {
      setIsProcessing(false)
    }
  }

  async function handleReset(): Promise<void> {
    try {
      setIsRunning(false)
      setIsProcessing(true)
      setSimulation(await resetSimulation())
      setError(null)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The simulation could not reset.')
    } finally {
      setIsProcessing(false)
    }
  }

  async function handleStrategyChange(strategy: SignalStrategy): Promise<void> {
    try {
      setIsRunning(false)
      setIsProcessing(true)
      setSimulation(await setSignalStrategy(strategy))
      setComparison(null)
      setError(null)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The signal strategy could not change.')
    } finally {
      setIsProcessing(false)
    }
  }

  async function handleComparison(): Promise<void> {
    try {
      setIsProcessing(true)
      setComparison(await compareStrategies())
      setError(null)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The strategy comparison could not run.')
    } finally {
      setIsProcessing(false)
    }
  }

  async function handleCloseAccident(): Promise<void> {
    try {
      setIsProcessing(true)
      setSimulation(await closeAccident(accidentRoadId))
      setError(null)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The road could not be closed.')
    } finally {
      setIsProcessing(false)
    }
  }

  async function handleReopenAccident(): Promise<void> {
    try {
      setIsProcessing(true)
      setSimulation(await reopenAccident(accidentRoadId))
      setError(null)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The road could not be reopened.')
    } finally {
      setIsProcessing(false)
    }
  }

  const metrics = simulation?.metrics
  const roadsByDensity = simulation
    ? [...simulation.roads].sort((left, right) => right.densityRatio - left.densityRatio).slice(0, 5)
    : []

  return (
    <main className="dashboard-shell">
      <header className="dashboard-header">
        <div>
          <p className="eyebrow">Live simulation dashboard</p>
          <h1>Traffic Flow Control</h1>
          <p className="header-copy">Graph routing, signal timing, and congestion in one city map.</p>
        </div>
        <div className={`connection-status ${error ? 'has-error' : ''}`}>
          <span aria-hidden="true" />
          {error ? 'API needs attention' : 'API connected'}
        </div>
      </header>

      {error && <p className="error-message" role="alert">{error}</p>}

      <section className="metric-grid" aria-label="Simulation metrics">
        <article className="metric-card">
          <span>Simulation time</span>
          <strong>{formatSeconds(simulation?.elapsedSeconds ?? 0)}</strong>
        </article>
        <article className="metric-card">
          <span>Completed trips</span>
          <strong>{metrics?.completedVehicles ?? 0}</strong>
        </article>
        <article className="metric-card">
          <span>Average wait</span>
          <strong>{formatSeconds(metrics?.averageWaitingTimeSeconds ?? 0)}</strong>
        </article>
        <article className="metric-card">
          <span>Maximum queue</span>
          <strong>{metrics?.maximumQueueLength ?? 0}</strong>
        </article>
      </section>

      <section className="workspace-grid">
        <section className="map-panel" aria-labelledby="map-heading">
          <div className="panel-heading">
            <div>
              <p className="section-kicker">City network</p>
              <h2 id="map-heading">Live traffic map</h2>
            </div>
            <span className="vehicle-count">{simulation?.vehicleCounts.moving ?? 0} moving</span>
          </div>
          {network && simulation ? (
            <TrafficCanvas network={network} simulation={simulation} />
          ) : (
            <div className="map-loading">Connecting to the local simulation API…</div>
          )}
        </section>

        <aside className="control-panel" aria-label="Simulation controls">
          <div>
            <p className="section-kicker">Controls</p>
            <h2>Run a scenario</h2>
          </div>
          <label>
            Start intersection
            <select value={source} onChange={(event) => setSource(event.target.value)} disabled={!network}>
              {network?.intersections.map((intersection) => (
                <option key={intersection.id} value={intersection.id}>{intersection.id}</option>
              ))}
            </select>
          </label>
          <label>
            Destination
            <select value={destination} onChange={(event) => setDestination(event.target.value)} disabled={!network}>
              {network?.intersections.map((intersection) => (
                <option key={intersection.id} value={intersection.id}>{intersection.id}</option>
              ))}
            </select>
          </label>
          <label>
            Signal strategy
            <select
              value={simulation?.signalStrategy ?? 'fixed'}
              onChange={(event) => void handleStrategyChange(event.target.value as SignalStrategy)}
              disabled={isProcessing || !simulation}
            >
              <option value="fixed">Fixed cycle</option>
              <option value="adaptive">Adaptive queues</option>
            </select>
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={emergency}
              onChange={(event) => setEmergency(event.target.checked)}
            />
            Emergency vehicle priority
          </label>
          <p className="strategy-copy">
            {simulation?.signalStrategy === 'adaptive'
              ? 'Greedy controller: gives the larger queued approach priority after its minimum green time.'
              : 'Predictable controller: alternates horizontal and vertical green phases on a fixed schedule.'}
          </p>
          <button className="primary-button" type="button" onClick={() => void handleAddVehicle()} disabled={isProcessing || !network}>
            Add vehicle
          </button>
          <div className="button-row">
            <button type="button" onClick={() => void advance(1)} disabled={isProcessing || !simulation}>Step 1s</button>
            <button type="button" onClick={() => void advance(10)} disabled={isProcessing || !simulation}>Step 10s</button>
          </div>
          <button className={isRunning ? 'pause-button' : 'primary-button'} type="button" onClick={() => setIsRunning((current) => !current)} disabled={!simulation}>
            {isRunning ? 'Pause live run' : 'Run live'}
          </button>
          <button className="reset-button" type="button" onClick={() => void handleReset()} disabled={isProcessing || !simulation}>Reset simulation</button>
          <button type="button" onClick={() => void handleComparison()} disabled={isProcessing || !network}>
            Compare strategies
          </button>
          <label>
            Accident road
            <select value={accidentRoadId} onChange={(event) => setAccidentRoadId(event.target.value)} disabled={!network}>
              {network?.roads.map((road) => (
                <option key={road.id} value={road.id}>{road.id} · {road.from} → {road.to}</option>
              ))}
            </select>
          </label>
          <div className="button-row">
            <button type="button" onClick={() => void handleCloseAccident()} disabled={isProcessing || !simulation}>Close road</button>
            <button type="button" onClick={() => void handleReopenAccident()} disabled={isProcessing || !simulation}>Reopen road</button>
          </div>
          <p className="control-hint">Vehicles follow Dijkstra routes and wait at red lights or full downstream roads.</p>
        </aside>
      </section>

      <section className="road-panel" aria-labelledby="roads-heading">
        <div className="panel-heading">
          <div>
            <p className="section-kicker">Congestion watch</p>
            <h2 id="roads-heading">Most occupied roads</h2>
          </div>
          <span>{formatSeconds(metrics?.totalWaitingTimeSeconds ?? 0)} total waiting</span>
        </div>
        {comparison && (
          <section className="comparison-panel" aria-label="Fixed and adaptive strategy comparison">
            <div className="comparison-heading">
              <strong>Equal-demand comparison</strong>
              <span>{comparison.vehicleCount} vehicles · {formatSeconds(comparison.durationSeconds)}</span>
            </div>
            <div className="comparison-grid">
              {(['fixed', 'adaptive'] as const).map((strategy) => {
                const result = comparison.results[strategy]
                return (
                  <article className={strategy === 'adaptive' ? 'comparison-result is-adaptive' : 'comparison-result'} key={strategy}>
                    <span>{strategy === 'adaptive' ? 'Adaptive queues' : 'Fixed cycle'}</span>
                    <strong>{formatSeconds(result.averageWaitingTimeSeconds)} avg. wait</strong>
                    <small>{result.completedVehicles} completed · queue peak {result.maximumQueueLength}</small>
                  </article>
                )
              })}
            </div>
          </section>
        )}
        <div className="road-list">
          {roadsByDensity.map((road) => (
            <div className="road-row" key={road.id}>
              <strong>{road.id}</strong>
              <div className="density-track" aria-label={`${road.id} is ${Math.round(road.densityRatio * 100)} percent full`}>
                <span style={{ width: `${Math.min(100, road.densityRatio * 100)}%` }} />
              </div>
              <span>{road.occupancy}/{road.capacity}</span>
              <span>{Math.round(road.densityRatio * 100)}%</span>
            </div>
          ))}
        </div>
      </section>
    </main>
  )
}

export default App
