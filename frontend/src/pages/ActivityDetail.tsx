import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { MapContainer, TileLayer, Polyline } from 'react-leaflet'
import { useFilters } from '../store/filters'
import { api } from '../lib/api'
import Chart from '../components/Chart'
import LoadingError from '../components/LoadingError'

type ColorBy = 'pace' | 'heart_rate' | 'altitude'

// Garmin percentile colors: <5% red, 5-29% orange, 30-69% green, 70-95% blue, >95% purple
const ZONE_COLORS: Record<string, string> = {
  walking: '#aaaaaa', poor: '#e53935', fair: '#ff9800',
  moderate: '#43a047', good: '#1e88e5', excellent: '#8e24aa',
}

function lerp(a: number, b: number, t: number) { return a + (b - a) * t }

function valueToColor(v: number, min: number, max: number): string {
  // RdYlGn_r: red (low/bad) → yellow → green (high/good) for HR/pace (inverted)
  const t = max === min ? 0.5 : (v - min) / (max - min)
  const r = Math.round(lerp(26, 215, t))
  const g = Math.round(lerp(152, 48, t))
  const bv = Math.round(lerp(80, 31, t))
  return `rgb(${r},${g},${bv})`
}

export default function ActivityDetail() {
  const filters = useFilters()
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [colorBy, setColorBy] = useState<ColorBy>('pace')

  const { data: actsData, isLoading: actsLoading } = useQuery({
    queryKey: ['fit-activities', filters.start, filters.end, filters.types],
    queryFn: () => api.fitActivities(filters),
    enabled: !!filters.start,
  })

  const activities = actsData?.activities ?? []
  const actId = selectedId ?? (activities[0]?.activity_id ?? null)

  const { data: fitData, isLoading: fitLoading, error: fitError } = useQuery({
    queryKey: ['fit-detail', actId],
    queryFn: () => api.fitDetail(actId!),
    enabled: actId != null,
  })

  const { data: decData } = useQuery({
    queryKey: ['fit-decoupling', actId],
    queryFn: () => api.fitDecoupling(actId!),
    enabled: actId != null,
  })

  if (actsLoading) return <LoadingError loading />

  const records = fitData?.records ?? []
  const hasGps = fitData?.has_gps && records.some((r: any) => r.lat != null)

  // Map track
  const gpsRecs = records.filter((r: any) => r.lat != null && r.lon != null && !r.is_walking)
  const colorField = colorBy === 'pace' ? 'pace' : colorBy
  const colorVals = gpsRecs.map((r: any) => r[colorField] ?? 0).filter(Boolean)
  const cMin = Math.min(...colorVals)
  const cMax = Math.max(...colorVals)
  // Bounding box for auto-fit
  const allLats = gpsRecs.map((r: any) => r.lat)
  const allLons = gpsRecs.map((r: any) => r.lon)
  const mapBounds: [[number, number], [number, number]] = allLats.length > 0
    ? [[Math.min(...allLats), Math.min(...allLons)], [Math.max(...allLats), Math.max(...allLons)]]
    : [[50.6, 5.5], [50.65, 5.6]]

  // First 2km vs last 2km segment comparison
  const runRecords = records.filter((r: any) => !r.is_walking && r.distance_km != null)
  const totalKm = runRecords.length > 0 ? runRecords[runRecords.length - 1].distance_km : 0
  const segKm = Math.min(2, totalKm / 3)  // use smaller window on short runs
  const firstSeg = runRecords.filter((r: any) => r.distance_km <= segKm)
  const lastSeg  = runRecords.filter((r: any) => r.distance_km >= totalKm - segKm)

  function segAvg(recs: any[], field: string) {
    const vals = recs.map((r: any) => r[field]).filter((v: any) => v != null && !isNaN(v))
    return vals.length > 0 ? vals.reduce((a: number, b: number) => a + b, 0) / vals.length : null
  }
  function fmtPace(v: number | null) {
    if (!v) return '-'
    const m = Math.floor(v); const s = Math.round((v - m) * 60).toString().padStart(2, '0')
    return `${m}:${s} /km`
  }


  // Use grade-adjusted pace when altitude data is available (trail running)
  const hasGap = runRecords.some((r: any) => r.gap != null)
  const paceField = hasGap ? 'gap' : 'pace'
  const paceLabel = hasGap ? 'GAP' : 'Pace'

  const segMetrics = firstSeg.length >= 5 && lastSeg.length >= 5 ? [
    {
      label: paceLabel,
      first: segAvg(firstSeg, paceField),
      last:  segAvg(lastSeg,  paceField),
      fmt: fmtPace,
      lowerIsBetter: true,
    },
    {
      label: 'Cadence',
      first: segAvg(firstSeg, 'cadence_spm'),
      last:  segAvg(lastSeg,  'cadence_spm'),
      fmt: (v: number | null) => v ? `${v.toFixed(0)} spm` : '-',
      lowerIsBetter: false,
    },
    {
      label: 'Vert. Osc.',
      first: segAvg(firstSeg, 'vertical_oscillation'),
      last:  segAvg(lastSeg,  'vertical_oscillation'),
      fmt: (v: number | null) => v ? `${v.toFixed(1)} cm` : '-',
      lowerIsBetter: true,
    },
  ] : []

  const CHARTS: { col: string; label: string; zoneKey?: string; reversed?: boolean; fmtAvg: (v: number) => string }[] = [
    { col: 'heart_rate',          label: 'HR (bpm)',                   fmtAvg: v => `${Math.round(v)} bpm` },
    { col: 'gap',                 label: `${paceLabel} (min/km)`,      reversed: true, fmtAvg: v => fmtPace(v) },
    { col: 'cadence_spm',         label: 'Cadence (spm)',              zoneKey: 'cadence_spm_zone',           fmtAvg: v => `${Math.round(v)} spm` },
    { col: 'vertical_ratio',      label: 'Vertical Ratio (%)',         zoneKey: 'vertical_ratio_zone',        fmtAvg: v => `${v.toFixed(1)}%` },
    { col: 'ground_contact_time', label: 'Ground Contact Time (ms)',   zoneKey: 'ground_contact_time_zone',   fmtAvg: v => `${Math.round(v)} ms` },
    { col: 'vertical_oscillation',label: 'Vertical Oscillation (cm)',  zoneKey: 'vertical_oscillation_zone',  fmtAvg: v => `${v.toFixed(1)} cm` },
    { col: 'stride_length',       label: 'Stride Length (m)',          fmtAvg: v => `${v.toFixed(2)} m` },
  ]

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold text-white">Activity Detail</h2>

      {activities.length === 0 ? (
        <LoadingError empty emptyMsg="No activities in selected range." />
      ) : (
        <>
          <select
            value={actId ?? ''}
            onChange={e => setSelectedId(Number(e.target.value))}
            className="w-full bg-garmin-surface border border-garmin-border rounded px-3 py-2 text-garmin-text focus:outline-none focus:border-garmin-blue"
          >
            {activities.map((a: any) => (
              <option key={a.activity_id} value={a.activity_id}>{a.label}</option>
            ))}
          </select>


          {decData?.decoupling != null && (
            <div className={`rounded-lg px-4 py-3 text-sm border ${
              decData.level === 'good' ? 'bg-green-900/30 border-green-700 text-green-300' :
              decData.level === 'borderline' ? 'bg-yellow-900/30 border-yellow-700 text-yellow-300' :
              'bg-red-900/30 border-red-700 text-red-300'
            }`}>
              <p className="font-medium mb-1">Aerobic Decoupling ({decData.label})</p>
              <p className="opacity-80">
                Aerobic decoupling measures cardiac drift, meaning how much your heart rate rises relative to pace during the run.
                It compares your Efficiency Factor (pace ÷ HR) in the first half versus the second half.
                Below 5% means your aerobic system handled the effort without drifting. Your base is solid for this pace.
                Above 10% means your heart was working progressively harder to maintain the same speed, a sign the effort
                was beyond your current aerobic capacity. Uses grade-adjusted pace so trail climbs don't distort the result.
                Most reliable on flat or rolling terrain. On runs where D+ is heavily front- or back-loaded, cardiac drift
                may still reflect elevation distribution rather than true aerobic fatigue.
              </p>
            </div>
          )}

          {segMetrics.length > 0 && (
            <div className="bg-garmin-surface border border-garmin-border rounded-lg p-4">
              <p className="text-sm font-medium text-white mb-3">
                Start vs End ({segKm.toFixed(1)} km segments, muscular endurance check)
              </p>
              <div className="grid grid-cols-3 gap-3">
                {segMetrics.map(({ label, first, last, fmt, lowerIsBetter }) => {
                  const delta = first != null && last != null ? last - first : null
                  // for pace: positive delta = slower = bad. for cadence: negative = bad.
                  const degraded = delta != null && (lowerIsBetter ? delta > 0.03 : delta < -1)
                  const improved = delta != null && (lowerIsBetter ? delta < -0.03 : delta > 1)
                  return (
                    <div key={label} className="text-center">
                      <p className="text-garmin-muted text-xs mb-2">{label}</p>
                      <div className="flex items-center justify-center gap-2 text-sm">
                        <div className="text-center">
                          <p className="text-xs text-garmin-muted">First</p>
                          <p className="text-white font-medium">{fmt(first)}</p>
                        </div>
                        <div className={`text-lg ${degraded ? 'text-red-400' : improved ? 'text-green-400' : 'text-garmin-muted'}`}>
                          {degraded ? '↓' : improved ? '↑' : '→'}
                        </div>
                        <div className="text-center">
                          <p className="text-xs text-garmin-muted">Last</p>
                          <p className={`font-medium ${degraded ? 'text-red-400' : improved ? 'text-green-400' : 'text-white'}`}>
                            {fmt(last)}
                          </p>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
              <p className="text-garmin-muted text-xs mt-3">
                Cadence or pace degrading in the last km means muscular endurance is the bottleneck. Holding form until the final meter means your fitness has leveled up.
              </p>
            </div>
          )}

          {fitLoading ? <LoadingError loading /> : fitError ? (
            <LoadingError empty emptyMsg="No FIT data found for this activity." />
          ) : (
            <>
              {hasGps && (
                <div>
                  <div className="flex gap-4 mb-2 text-sm flex-wrap">
                    {(['pace', 'heart_rate', 'altitude'] as ColorBy[]).map(c => (
                      <button key={c}
                        onClick={() => setColorBy(c)}
                        className={`px-3 py-1 rounded transition-colors ${colorBy === c ? 'bg-garmin-blue text-white' : 'bg-garmin-surface text-garmin-muted hover:text-white'}`}
                      >
                        {c === 'heart_rate' ? 'Heart Rate' : c.charAt(0).toUpperCase() + c.slice(1)}
                      </button>
                    ))}
                  </div>
                  <div className="rounded-lg overflow-hidden border border-garmin-border" style={{ height: 420 }}>
                    <MapContainer
                      bounds={mapBounds}
                      boundsOptions={{ padding: [20, 20] }}
                      style={{ height: '100%', width: '100%' }}
                    >
                      <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" />
                      {gpsRecs.slice(0, -1).map((r: any, i: number) => {
                        const next = gpsRecs[i + 1]
                        if (!next) return null
                        const v = r[colorField] ?? 0
                        const color = valueToColor(
                          colorBy === 'pace' ? (cMax + cMin - v) : v,
                          cMin, cMax
                        )
                        return (
                          <Polyline
                            key={i}
                            positions={[[r.lat, r.lon], [next.lat, next.lon]]}
                            pathOptions={{ color, weight: 3, opacity: 0.85 }}
                          />
                        )
                      })}
                    </MapContainer>
                  </div>
                </div>
              )}

              <p className="text-garmin-muted text-xs">
                Color bands match Garmin's percentile zones: red &lt;5%, orange 5–29%, yellow 30–69%, light green 70–95%, dark green &gt;95%.
                Cadence: &lt;151 / 151–162 / 163–173 / 174–185 / &gt;185 spm.
                GCT: &gt;305 / 273–305 / 241–272 / 208–240 / &lt;208 ms.
                Vertical Ratio: &gt;10.1 / 8.7–10.1 / 7.5–8.6 / 6.1–7.4 / &lt;6.1 %.
                Thresholds for cadence, vertical oscillation, and GCT are relaxed on uphills to avoid penalising climbing effort.
                Grey markers are walking segments excluded from zone evaluation.
              </p>

              <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                {CHARTS.map(({ col, label, zoneKey, reversed, fmtAvg }) => {
                  const pts = records.filter((r: any) => r[col] != null && r.distance_km != null)
                  if (pts.length === 0) return null

                  const runPts = pts.filter((r: any) => !r.is_walking)
                  const walkPts = pts.filter((r: any) => r.is_walking)
                  const avg = segAvg(runPts, col)
                  const chartTitle = avg != null ? `${label} (avg ${fmtAvg(avg)})` : label

                  const altPts = records.filter((r: any) => r.altitude != null && r.distance_km != null)

                  const traces: any[] = []

                  // Elevation backdrop
                  if (altPts.length > 0) {
                    traces.push({
                      type: 'scatter', mode: 'none', name: 'Elevation',
                      x: altPts.map((r: any) => r.distance_km),
                      y: altPts.map((r: any) => r.altitude),
                      fill: 'tozeroy', fillcolor: 'rgba(180,180,180,0.12)',
                      yaxis: 'y2', showlegend: false, hoverinfo: 'skip',
                    })
                  }

                  if (zoneKey) {
                    const zones = ['poor', 'fair', 'moderate', 'good', 'excellent']
                    zones.forEach(zone => {
                      const zPts = runPts.filter((r: any) => r[zoneKey] === zone)
                      if (zPts.length > 0) {
                        traces.push({
                          type: 'scatter', mode: 'markers', name: zone,
                          x: zPts.map((r: any) => r.distance_km),
                          y: zPts.map((r: any) => r[col]),
                          marker: { color: ZONE_COLORS[zone], size: 4, opacity: 0.8 },
                          hovertemplate: `${label}: %{y:.1f}<extra>${zone}</extra>`,
                        })
                      }
                    })
                  } else {
                    const lineColor = col === 'heart_rate' ? '#e53935' : '#1e88e5'
                    if (runPts.length > 0) {
                      traces.push({
                        type: 'scatter', mode: 'lines', name: label, showlegend: false,
                        x: runPts.map((r: any) => r.distance_km),
                        y: runPts.map((r: any) => r[col]),
                        line: { color: lineColor, width: 1.5 },
                      })
                    }
                  }

                  if (walkPts.length > 0) {
                    traces.push({
                      type: 'scatter', mode: 'markers', name: 'Walking',
                      x: walkPts.map((r: any) => r.distance_km),
                      y: walkPts.map((r: any) => r[col]),
                      marker: { color: '#aaaaaa', size: 3, opacity: 0.5 },
                      hoverinfo: 'skip', showlegend: false,
                    })
                  }

                  return (
                    <Chart
                      key={col}
                      title={chartTitle}
                      data={traces}
                      height={250}
                      layout={{
                        xaxis: { title: { text: 'Distance (km)' } },
                        yaxis: { title: { text: label }, autorange: reversed ? 'reversed' : undefined },
                        yaxis2: { overlaying: 'y', side: 'right', showticklabels: false, showgrid: false },
                        margin: { t: 35, b: 35, l: 50, r: 40 },
                      } as any}
                    />
                  )
                })}
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}
