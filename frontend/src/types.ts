export type Intersection = {
  id: string
  x: number
  y: number
}

export type SignalStrategy = 'fixed' | 'adaptive'

export type Road = {
  id: string
  from: string
  to: string
  lengthMeters: number
  speedLimitKmph: number
  lanes: number
  capacity: number
}

export type NetworkMap = {
  intersections: Intersection[]
  roads: Road[]
}

export type SignalState = {
  intersectionId: string
  strategy: SignalStrategy
  phase: string
  activeAxis: 'horizontal' | 'vertical' | null
  secondsUntilNextPhase: number
}

export type VehicleState = {
  id: string
  status: 'moving' | 'waiting' | 'completed'
  currentRoadId: string | null
  currentRoadIndex: number
  positionMeters: number
  travelTimeSeconds: number
  waitingTimeSeconds: number
  waitingReason: 'signal' | 'road_capacity' | 'accident' | null
  isEmergency: boolean
  source: string
  destination: string
}

export type RoadState = {
  id: string
  occupancy: number
  capacity: number
  densityRatio: number
  currentTravelTimeSeconds: number
}

export type SimulationMetrics = {
  totalVehicles: number
  completedVehicles: number
  totalWaitingTimeSeconds: number
  averageWaitingTimeSeconds: number
  totalTravelTimeSeconds: number
  averageCompletedTravelTimeSeconds: number
  averageRoadDensity: number
  maximumRoadDensity: number
  maximumQueueLength: number
}

export type SimulationState = {
  elapsedSeconds: number
  signalStrategy: SignalStrategy
  closedRoads: string[]
  vehicles: VehicleState[]
  signals: SignalState[]
  roads: RoadState[]
  queueLengths: Record<string, number>
  vehicleCounts: Record<VehicleState['status'], number>
  metrics: SimulationMetrics
}

export type StrategyComparison = {
  durationSeconds: number
  vehicleCount: number
  results: {
    fixed: Pick<
      SimulationMetrics,
      'completedVehicles' | 'averageWaitingTimeSeconds' | 'totalWaitingTimeSeconds' | 'maximumQueueLength'
    >
    adaptive: Pick<
      SimulationMetrics,
      'completedVehicles' | 'averageWaitingTimeSeconds' | 'totalWaitingTimeSeconds' | 'maximumQueueLength'
    >
  }
}
