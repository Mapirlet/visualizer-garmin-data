import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { MapContainer, TileLayer, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import 'leaflet.heat'
import { useFilters } from '../store/filters'
import { api } from '../lib/api'
import LoadingError from '../components/LoadingError'

// leaflet.heat adds L.heatLayer — extend type
declare module 'leaflet' {
  function heatLayer(
    latlngs: [number, number][],
    options?: { radius?: number; blur?: number; minOpacity?: number }
  ): L.Layer
}

function HeatLayer({ points, radius, blur }: { points: [number, number][]; radius: number; blur: number }) {
  const map = useMap()
  const layerRef = useRef<L.Layer | null>(null)

  useEffect(() => {
    if (layerRef.current) {
      map.removeLayer(layerRef.current)
      layerRef.current = null
    }
    if (points.length === 0) return
    layerRef.current = (L as any).heatLayer(points, { radius, blur, minOpacity: 0.3 }).addTo(map)
    return () => {
      if (layerRef.current) {
        try { map.removeLayer(layerRef.current) } catch {}
        layerRef.current = null
      }
    }
  }, [map, points, radius, blur])

  return null
}

export default function Routes() {
  const filters = useFilters()
  const [radius, setRadius] = useState(6)
  const [blur, setBlur] = useState(2)

  const { data, isLoading, error } = useQuery({
    queryKey: ['gps', filters.start, filters.end, filters.types],
    queryFn: () => api.gps(filters),
    enabled: !!filters.start,
  })

  if (isLoading) return <LoadingError loading />
  if (error) return <LoadingError error={error as Error} />
  if (!data?.has_data) {
    return <LoadingError cacheMsg="uv run python -m src.gps_cache" />
  }

  const points: [number, number][] = data?.points ?? []

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold text-white">Route Heatmap</h2>
      <p className="text-garmin-muted text-sm">
        {points.length.toLocaleString()} GPS points from {data?.activity_count} activities
      </p>

      <div className="flex gap-6 text-sm flex-wrap">
        <div className="flex items-center gap-2">
          <label className="text-garmin-muted">Heat radius</label>
          <input type="range" min={1} max={25} value={radius}
            onChange={e => setRadius(Number(e.target.value))} className="w-24" />
          <span className="text-white w-4">{radius}</span>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-garmin-muted">Blur</label>
          <input type="range" min={0} max={5} value={blur}
            onChange={e => setBlur(Number(e.target.value))} className="w-24" />
          <span className="text-white w-4">{blur}</span>
        </div>
      </div>

      <div className="rounded-lg overflow-hidden border border-garmin-border" style={{ height: 560 }}>
        <MapContainer
          center={[50.6326, 5.5797]}
          zoom={13}
          style={{ height: '100%', width: '100%' }}
        >
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            attribution='&copy; <a href="https://carto.com/">CARTO</a>'
          />
          {points.length > 0 && <HeatLayer points={points} radius={radius} blur={blur} />}
        </MapContainer>
      </div>
    </div>
  )
}
