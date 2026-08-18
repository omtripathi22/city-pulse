import { useEffect, useRef } from 'react'
import type { Intersection, NetworkMap, Road, SimulationState } from './types'

type TrafficCanvasProps = {
  network: NetworkMap
  simulation: SimulationState
}

type Point = {
  x: number
  y: number
}

const ROAD_COLORS = {
  free: '#37c98b',
  moderate: '#f6c453',
  congested: '#f27066',
  inactive: '#31465e',
}

function densityColor(density: number): string {
  if (density >= 0.75) return ROAD_COLORS.congested
  if (density >= 0.4) return ROAD_COLORS.moderate
  return ROAD_COLORS.free
}

function laneOffset(from: Point, to: Point): Point {
  const dx = to.x - from.x
  const dy = to.y - from.y
  const length = Math.hypot(dx, dy) || 1
  return { x: (-dy / length) * 4, y: (dx / length) * 4 }
}

function drawRoadArrow(context: CanvasRenderingContext2D, from: Point, to: Point): void {
  const arrowPoint = {
    x: from.x + (to.x - from.x) * 0.63,
    y: from.y + (to.y - from.y) * 0.63,
  }
  const angle = Math.atan2(to.y - from.y, to.x - from.x)
  const arrowSize = 5

  context.save()
  context.translate(arrowPoint.x, arrowPoint.y)
  context.rotate(angle)
  context.beginPath()
  context.moveTo(arrowSize, 0)
  context.lineTo(-arrowSize, -arrowSize * 0.65)
  context.lineTo(-arrowSize, arrowSize * 0.65)
  context.closePath()
  context.fill()
  context.restore()
}

function TrafficCanvas({ network, simulation }: TrafficCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return undefined

    const draw = () => {
      const context = canvas.getContext('2d')
      if (!context) return

      const width = canvas.clientWidth
      const height = canvas.clientHeight
      const pixelRatio = window.devicePixelRatio || 1
      canvas.width = Math.max(1, Math.floor(width * pixelRatio))
      canvas.height = Math.max(1, Math.floor(height * pixelRatio))
      context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)
      context.clearRect(0, 0, width, height)
      context.fillStyle = '#091422'
      context.fillRect(0, 0, width, height)

      const xValues = network.intersections.map((intersection) => intersection.x)
      const yValues = network.intersections.map((intersection) => intersection.y)
      const minX = Math.min(...xValues)
      const maxX = Math.max(...xValues)
      const minY = Math.min(...yValues)
      const maxY = Math.max(...yValues)
      const padding = 58
      const scale = Math.min(
        (width - padding * 2) / Math.max(1, maxX - minX),
        (height - padding * 2) / Math.max(1, maxY - minY),
      )
      const mapOffsetX = (width - (maxX - minX) * scale) / 2 - minX * scale
      const mapOffsetY = (height - (maxY - minY) * scale) / 2 - minY * scale
      const intersections = new Map(network.intersections.map((item) => [item.id, item]))
      const roadStates = new Map(simulation.roads.map((item) => [item.id, item]))
      const closedRoads = new Set(simulation.closedRoads)
      const signals = new Map(simulation.signals.map((item) => [item.intersectionId, item]))

      const project = (intersection: Intersection): Point => ({
        x: intersection.x * scale + mapOffsetX,
        y: intersection.y * scale + mapOffsetY,
      })

      const roadPoints = (road: Road): { from: Point; to: Point } | null => {
        const source = intersections.get(road.from)
        const destination = intersections.get(road.to)
        if (!source || !destination) return null
        const rawFrom = project(source)
        const rawTo = project(destination)
        const offset = laneOffset(rawFrom, rawTo)
        return {
          from: { x: rawFrom.x + offset.x, y: rawFrom.y + offset.y },
          to: { x: rawTo.x + offset.x, y: rawTo.y + offset.y },
        }
      }

      for (const road of network.roads) {
        const points = roadPoints(road)
        if (!points) continue
        const state = roadStates.get(road.id)
        const isClosed = closedRoads.has(road.id)
        context.strokeStyle = isClosed
          ? '#d15b62'
          : state
            ? densityColor(state.densityRatio)
            : ROAD_COLORS.inactive
        context.fillStyle = context.strokeStyle
        context.lineWidth = state?.occupancy ? 7 : 5
        context.lineCap = 'round'
        context.setLineDash(isClosed ? [8, 7] : [])
        context.beginPath()
        context.moveTo(points.from.x, points.from.y)
        context.lineTo(points.to.x, points.to.y)
        context.stroke()
        context.setLineDash([])
        if (!isClosed) drawRoadArrow(context, points.from, points.to)
      }

      for (const vehicle of simulation.vehicles) {
        if (!vehicle.currentRoadId) continue
        const road = network.roads.find((item) => item.id === vehicle.currentRoadId)
        if (!road) continue
        const points = roadPoints(road)
        if (!points) continue
        const progress = Math.min(1, vehicle.positionMeters / road.lengthMeters)
        const x = points.from.x + (points.to.x - points.from.x) * progress
        const y = points.from.y + (points.to.y - points.from.y) * progress
        const angle = Math.atan2(points.to.y - points.from.y, points.to.x - points.from.x)

        context.save()
        context.translate(x, y)
        context.rotate(angle)
        context.fillStyle = vehicle.isEmergency
          ? '#ff6b6b'
          : vehicle.status === 'waiting'
            ? '#f6c453'
            : '#71a6ff'
        context.fillRect(-6, -4, 12, 8)
        context.fillStyle = '#eaf2ff'
        context.fillRect(1, -2.5, 3, 5)
        if (vehicle.isEmergency) {
          context.fillStyle = '#fff4d6'
          context.fillRect(-2, -3, 4, 6)
          context.fillRect(-4, -1, 8, 2)
        }
        context.restore()
      }

      for (const intersection of network.intersections) {
        const point = project(intersection)
        const signal = signals.get(intersection.id)
        const isYellow = signal?.phase.includes('yellow')
        const signalColor = isYellow
          ? '#f6c453'
          : signal?.activeAxis
            ? '#37c98b'
            : '#f27066'

        context.fillStyle = '#12243a'
        context.beginPath()
        context.arc(point.x, point.y, 14, 0, Math.PI * 2)
        context.fill()
        context.strokeStyle = '#8fa9ca'
        context.lineWidth = 1.5
        context.stroke()
        context.fillStyle = signalColor
        context.beginPath()
        context.arc(point.x, point.y, 6, 0, Math.PI * 2)
        context.fill()
        context.fillStyle = '#e7f0ff'
        context.font = '600 12px system-ui, sans-serif'
        context.textAlign = 'center'
        context.fillText(intersection.id, point.x, point.y - 23)
      }

      context.font = '500 12px system-ui, sans-serif'
      context.textAlign = 'left'
      context.fillStyle = '#adbed7'
      context.fillText('Road density', 18, height - 24)
      const legend = [
        ['Free', ROAD_COLORS.free],
        ['Busy', ROAD_COLORS.moderate],
        ['Congested', ROAD_COLORS.congested],
      ] as const
      let legendX = 102
      for (const [label, color] of legend) {
        context.fillStyle = color
        context.fillRect(legendX, height - 34, 16, 4)
        context.fillStyle = '#d9e6f8'
        context.fillText(label, legendX + 22, height - 24)
        legendX += label === 'Congested' ? 0 : 78
      }
    }

    const observer = new ResizeObserver(draw)
    observer.observe(canvas)
    draw()
    return () => observer.disconnect()
  }, [network, simulation])

  return (
    <canvas
      ref={canvasRef}
      className="traffic-canvas"
      aria-label="Live traffic map showing roads, intersections, signal phases, and vehicle positions"
      role="img"
    >
      Live traffic map
    </canvas>
  )
}

export default TrafficCanvas
