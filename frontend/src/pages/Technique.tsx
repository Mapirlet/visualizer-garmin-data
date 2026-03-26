import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useFilters } from '../store/filters'
import { api } from '../lib/api'
import Chart from '../components/Chart'
import LoadingError from '../components/LoadingError'

const METRICS: { key: string; label: string }[] = [
  { key: 'avg_cadence', label: 'Cadence (spm)' },
  { key: 'avg_vertical_oscillation', label: 'Vertical Oscillation (cm)' },
  { key: 'avg_ground_contact_time', label: 'Ground Contact Time (ms)' },
  { key: 'avg_stride_length', label: 'Stride Length (cm)' },
  { key: 'avg_vertical_ratio', label: 'Vertical Ratio (%)' },
]

const TYPE_COLORS = ['#2196F3', '#4CAF50', '#FF9800', '#E91E63', '#9C27B0']

export default function Technique() {
  const filters = useFilters()
  const [smoothing, setSmoothing] = useState(7)
  const [xMetric, setXMetric] = useState('avg_cadence')
  const [yMetric, setYMetric] = useState('avg_hr')

  const { data, isLoading, error } = useQuery({
    queryKey: ['technique', filters.start, filters.end, filters.types],
    queryFn: () => api.technique(filters),
    enabled: !!filters.start,
  })

  const { data: corrData } = useQuery({
    queryKey: ['technique-corr', filters.start, filters.end, filters.types],
    queryFn: () => api.techniqueCorrelations(filters),
    enabled: !!filters.start,
  })

  const { data: scatterData } = useQuery({
    queryKey: ['technique-scatter', filters.start, filters.end, filters.types, xMetric, yMetric],
    queryFn: () => api.techniqueScatter(filters, xMetric, yMetric),
    enabled: !!filters.start,
  })

  if (isLoading) return <LoadingError loading />
  if (error) return <LoadingError error={error as Error} />

  if (!data?.has_data) {
    return <LoadingError cacheMsg="uv run python -m src.cache" />
  }

  const rows = data.rows ?? []
  if (rows.length === 0) return <LoadingError empty />

  const types = [...new Set(rows.map((r: any) => r.activity_type))]

  const hasGap = rows.some((r: any) => r.avg_gap_min_km != null)
  const allMetricKeys = ['avg_hr', 'avg_pace_min_km', ...(hasGap ? ['avg_gap_min_km'] : []), ...METRICS.map(m => m.key)]
  const allMetricLabels: Record<string, string> = {
    avg_hr: 'HR (bpm)',
    avg_pace_min_km: 'Pace (min/km)',
    avg_gap_min_km: 'GAP (min/km)',
    ...Object.fromEntries(METRICS.map(m => [m.key, m.label])),
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-white">Running Technique (walk segments removed)</h2>

      <div className="flex items-center gap-3 text-sm">
        <label className="text-garmin-muted">Rolling average</label>
        <input
          type="range" min={1} max={30} value={smoothing}
          onChange={e => setSmoothing(Number(e.target.value))}
          className="w-32"
        />
        <span className="text-white">{smoothing} days</span>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {METRICS.map(({ key, label }) => {
          const traces: any[] = types.flatMap((t: any, i) => {
            const grp = rows.filter((r: any) => r.activity_type === t && r[key] != null)
            if (grp.length === 0) return []
            const color = TYPE_COLORS[i % TYPE_COLORS.length]
            // Simple client-side rolling average by day index
            const sorted = [...grp].sort((a: any, b: any) => a.date.localeCompare(b.date))
            const yVals = sorted.map((r: any) => r[key])
            const smoothed = yVals.map((_: any, idx: number) => {
              const slice = yVals.slice(Math.max(0, idx - smoothing + 1), idx + 1)
              return slice.reduce((a: number, b: number) => a + b, 0) / slice.length
            })
            return [
              {
                type: 'scatter', mode: 'markers', name: t, legendgroup: t,
                x: sorted.map((r: any) => r.date), y: yVals,
                marker: { color, size: 5, opacity: 0.4 },
                hovertemplate: `${t}<br>%{x}<br>${label}: %{y:.1f}<extra></extra>`,
              },
              {
                type: 'scatter', mode: 'lines', name: `${t} trend`, legendgroup: t, showlegend: false,
                x: sorted.map((r: any) => r.date), y: smoothed,
                line: { color, width: 2 },
                hoverinfo: 'skip',
              },
            ]
          })
          return (
            <Chart
              key={key}
              title={label}
              data={traces}
              height={280}
              layout={{
                xaxis: { title: { text: 'Date' } },
                yaxis: { title: { text: label } },
                margin: { t: 35, b: 35, l: 50, r: 20 },
              }}
            />
          )
        })}
      </div>

      <div>
        <h3 className="text-base font-medium text-white mb-1">Correlation Matrix</h3>
        <p className="text-garmin-muted text-sm mb-3">
          Pearson r between all metrics. Red is positive correlation, blue is negative.
        </p>
        {corrData?.has_data && (
          <Chart
            data={[{
              type: 'heatmap',
              z: corrData.matrix,
              x: corrData.labels,
              y: corrData.labels,
              colorscale: 'RdBu',
              zmid: 0 as any,
              zmin: -1, zmax: 1,
              text: corrData.matrix.map((row: number[]) => row.map((v: number) => v.toFixed(2))),
              texttemplate: '%{text}',
              hovertemplate: '%{y} vs %{x}<br>r = %{z:.3f}<extra></extra>',
            } as any]}
            height={400}
            layout={{ margin: { t: 10, b: 80, l: 120, r: 20 } }}
          />
        )}
      </div>

      <div>
        <h3 className="text-base font-medium text-white mb-1">Drill-down Scatter</h3>
        <p className="text-garmin-muted text-sm mb-3">
          Presets for the most useful views, or pick any combination.
        </p>
        <div className="flex gap-2 mb-3 flex-wrap">
          {[
            { label: 'Technique Efficiency', x: hasGap ? 'avg_gap_min_km' : 'avg_pace_min_km', y: 'avg_vertical_oscillation',
              hint: 'Goal: run faster (lower GAP) while keeping oscillation below 9 cm. Uses grade-adjusted pace when altitude data is available.' },
            { label: 'Cadence vs HR', x: 'avg_cadence', y: 'avg_hr', hint: 'Higher cadence should come with lower HR at same pace' },
            { label: 'Stride vs GCT', x: 'avg_stride_length', y: 'avg_ground_contact_time', hint: 'Longer stride + shorter contact = better elastic reuse' },
          ].map(p => (
            <button key={p.label}
              onClick={() => { setXMetric(p.x); setYMetric(p.y) }}
              title={p.hint}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors border ${
                xMetric === p.x && yMetric === p.y
                  ? 'bg-garmin-blue border-garmin-blue text-white'
                  : 'bg-garmin-surface border-garmin-border text-garmin-muted hover:text-white'
              }`}>
              {p.label}
            </button>
          ))}
        </div>
        {(xMetric === 'avg_pace_min_km' || xMetric === 'avg_gap_min_km') && yMetric === 'avg_vertical_oscillation' && (
          <p className="text-garmin-muted text-xs mb-2">
            Points moving right and down over time means faster pace and lower bounce for pure efficiency gain.
            Points moving right and up means you are speeding up with brute force, not better mechanics.
          </p>
        )}
        <div className="flex gap-4 mb-3 text-sm flex-wrap">
          <div className="flex items-center gap-2">
            <label className="text-garmin-muted">X axis</label>
            <select value={xMetric} onChange={e => setXMetric(e.target.value)}
              className="bg-garmin-surface border border-garmin-border rounded px-2 py-1 text-garmin-text focus:outline-none focus:border-garmin-blue">
              {allMetricKeys.map(k => <option key={k} value={k}>{allMetricLabels[k]}</option>)}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-garmin-muted">Y axis</label>
            <select value={yMetric} onChange={e => setYMetric(e.target.value)}
              className="bg-garmin-surface border border-garmin-border rounded px-2 py-1 text-garmin-text focus:outline-none focus:border-garmin-blue">
              {allMetricKeys.map(k => <option key={k} value={k}>{allMetricLabels[k]}</option>)}
            </select>
          </div>
        </div>
        {scatterData && (
          <Chart
            data={[
              ...([...new Set((scatterData.points ?? []).map((p: any) => p.activity_type))].map((t: any, i) => ({
                type: 'scatter' as const,
                mode: 'markers' as const,
                name: t,
                x: scatterData.points.filter((p: any) => p.activity_type === t).map((p: any) => p[xMetric]),
                y: scatterData.points.filter((p: any) => p.activity_type === t).map((p: any) => p[yMetric]),
                marker: { color: TYPE_COLORS[i % TYPE_COLORS.length], size: 6, opacity: 0.8 },
              }))),
              ...(scatterData.trendlines ?? []).map((tl: any, i: number) => ({
                type: 'scatter' as const,
                mode: 'lines' as const,
                name: `${tl.activity_type} trend`,
                x: tl.x,
                y: tl.y,
                line: { color: TYPE_COLORS[i % TYPE_COLORS.length], width: 1.5, dash: 'dash' as const },
                showlegend: false,
              })),
            ]}
            layout={{
              xaxis: { title: { text: allMetricLabels[xMetric] } },
              yaxis: { title: { text: allMetricLabels[yMetric] } },
              ...((xMetric === 'avg_pace_min_km' || xMetric === 'avg_gap_min_km') && yMetric === 'avg_vertical_oscillation' ? {
                shapes: [{ type: 'line', x0: 0, x1: 1, xref: 'paper', y0: 9, y1: 9,
                  line: { color: '#43a047', dash: 'dash', width: 1 } }],
                annotations: [{ x: 1, xref: 'paper', y: 9, text: 'Goal: 9 cm',
                  showarrow: false, xanchor: 'right', font: { color: '#43a047', size: 11 } }],
              } : {}),
            } as any}
          />
        )}
      </div>
    </div>
  )
}
