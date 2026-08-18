import type { NetworkMap, SimulationState, StrategyComparison, VehicleState } from './types'

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000').replace(
  /\/$/,
  '',
)

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, options)

  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null)
    const detail =
      typeof payload === 'object' &&
      payload !== null &&
      'detail' in payload &&
      typeof payload.detail === 'string'
        ? payload.detail
        : response.statusText
    throw new Error(detail)
  }

  return response.json() as Promise<T>
}

export function getNetwork(): Promise<NetworkMap> {
  return request<NetworkMap>('/network')
}

export function getSimulationState(): Promise<SimulationState> {
  return request<SimulationState>('/simulation/state')
}

export function addVehicle(
  source: string,
  destination: string,
  emergency = false,
): Promise<VehicleState> {
  const params = new URLSearchParams({ source, destination, emergency: String(emergency) })
  return request<VehicleState>(`/simulation/vehicles?${params}`, { method: 'POST' })
}

export function stepSimulation(seconds: number): Promise<SimulationState> {
  return request<SimulationState>(`/simulation/step?seconds=${seconds}`, { method: 'POST' })
}

export function resetSimulation(): Promise<SimulationState> {
  return request<SimulationState>('/simulation/reset', { method: 'POST' })
}

export function setSignalStrategy(strategy: 'fixed' | 'adaptive'): Promise<SimulationState> {
  return request<SimulationState>(`/simulation/strategy?strategy=${strategy}`, { method: 'POST' })
}

export function compareStrategies(seconds = 180): Promise<StrategyComparison> {
  return request<StrategyComparison>(`/simulation/compare?seconds=${seconds}`, { method: 'POST' })
}

export function closeAccident(roadId: string): Promise<SimulationState> {
  return request<SimulationState>(`/simulation/accidents?road_id=${roadId}`, { method: 'POST' })
}

export function reopenAccident(roadId: string): Promise<SimulationState> {
  return request<SimulationState>(`/simulation/accidents/${roadId}`, { method: 'DELETE' })
}
