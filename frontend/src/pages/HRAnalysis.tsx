import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useFilters } from '../store/filters'
import { api } from '../lib/api'
import Chart from '../components/Chart'
import LoadingError from '../components/LoadingError'

const TYPE_COLORS = [
  '#2196F3', '#4CAF50', '#FF9800', '#E91E63',
  '#9C27B0', '#00BCD4', '#FF5722', '#8BC34A',
]

export default function HRAnalysis() {
  const filters = useFilters()
  const [paceMin, setPaceMin] = useState(3)
  const [paceMax, setPaceMax] = useState(10)

  const { data: paceData, isLoading: paceLoading, error: paceError } = useQuery({
    queryKey: ['hr-pace', filters.start, filters.end, filters.types],
    queryFn: () => api.hrPace(filters),
    enabled: !!filters.start,
  })

  const { data: efData, isLoading: efLoading } = useQuery({
    queryKey: ['efficiency', filters.start, filters.end, filters.types, paceMin, paceMax],
    queryFn: () => api.efficiency(filters, paceMin, paceMax),
    enabled: !!filters.start,
  })

  const { data: sleepData, isLoading: sleepLoading, error: sleepError } = useQuery({
    queryKey: ['hr-sleep', filters.start, filters.end, filters.types],
    queryFn: () => api.hrSleep(filters),
    enabled: !!filters.start,
  })

  const pacePoints = paceData?.points ?? []
  const paceTrendline = paceData?.trendline
  const paceTypes = [...new Set(pacePoints.map((p: any) => p.activity_type))]

  const scatterTraces: any[] = paceTypes.map((t: any, i) => ({
    type: 'scatter', mode: 'markers', name: t,
    x: pacePoints.filter((p: any) => p.activity_type === t).map((p: any) => p.avg_pace_min_km),
    y: pacePoints.filter((p: any) => p.activity_type === t).map((p: any) => p.avg_hr),
    text: pacePoints.filter((p: any) => p.activity_type === t).map((p: any) => p.name),
    marker: { color: TYPE_COLORS[i % TYPE_COLORS.length], size: 7, opacity: 0.8 },
    hovertemplate: '<b>%{text}</b><br>Pace: %{x:.2f} min/km<br>HR: %{y} bpm<extra></extra>',
  }))
  if (paceTrendline) {
    scatterTraces.push({
      type: 'scatter', mode: 'lines', name: 'OLS trend',
      x: paceTrendline.x, y: paceTrendline.y,
      line: { color: '#ffffff', width: 1.5, dash: 'dash' }, hovertemplate: '',
    })
  }

  const sleepPoints = sleepData?.points ?? []
  const sleepTrendline = sleepData?.trendline
  const sleepTypes = [...new Set(sleepPoints.map((p: any) => p.activity_type))]
  const sleepTraces: any[] = sleepTypes.map((t: any, i) => ({
    type: 'scatter', mode: 'markers', name: t,
    x: sleepPoints.filter((p: any) => p.activity_type === t).map((p: any) => p.avg_hr),
    y: sleepPoints.filter((p: any) => p.activity_type === t).map((p: any) => p.overall_score),
    text: sleepPoints.filter((p: any) => p.activity_type === t).map((p: any) => p.name),
    marker: { color: TYPE_COLORS[i % TYPE_COLORS.length], size: 7, opacity: 0.8 },
    hovertemplate: '<b>%{text}</b><br>HR: %{x} bpm<br>Sleep score: %{y}<extra></extra>',
  }))
  if (sleepTrendline) {
    sleepTraces.push({
      type: 'scatter', mode: 'lines', name: 'OLS trend',
      x: sleepTrendline.x, y: sleepTrendline.y,
      line: { color: '#ffffff', width: 1.5, dash: 'dash' }, hovertemplate: '',
    })
  }

  const efPoints = efData?.points ?? []

  return (
    <div className="space-y-10">
      {/* HR vs Pace */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold text-white">
          HR vs Pace {paceData?.has_technique ? '(walk segments removed)' : '(raw averages)'}
        </h2>
        {paceLoading ? <LoadingError loading /> : paceError ? <LoadingError error={paceError as Error} /> :
          pacePoints.length === 0
            ? <LoadingError empty emptyMsg="No running activities in selected range." />
            : <Chart
                data={scatterTraces}
                layout={{
                  xaxis: { title: { text: 'Pace (min/km)' } },
                  yaxis: { title: { text: 'HR (bpm)' } },
                }}
              />
        }

        <div>
          <h3 className="text-base font-medium text-white mb-1">Aerobic Efficiency Over Time</h3>
          <p className="text-garmin-muted text-sm mb-3">
            Efficiency Factor is speed (m/s) divided by HR. Higher means fitter. Filter to a pace band to control for effort.
          </p>
          <div className="flex gap-4 items-center mb-3 text-sm">
            <label className="text-garmin-muted">Pace band</label>
            <input type="number" value={paceMin} step={0.5} min={2} max={paceMax - 0.5}
              onChange={e => setPaceMin(Number(e.target.value))}
              className="w-16 bg-garmin-surface border border-garmin-border rounded px-2 py-1 text-garmin-text focus:outline-none focus:border-garmin-blue" />
            <span className="text-garmin-muted">to</span>
            <input type="number" value={paceMax} step={0.5} min={paceMin + 0.5} max={20}
              onChange={e => setPaceMax(Number(e.target.value))}
              className="w-16 bg-garmin-surface border border-garmin-border rounded px-2 py-1 text-garmin-text focus:outline-none focus:border-garmin-blue" />
            <span className="text-garmin-muted">min/km</span>
          </div>
          {efLoading ? <LoadingError loading /> : efPoints.length === 0
            ? <LoadingError empty emptyMsg="No data in this pace band." />
            : <Chart
                data={[
                  {
                    type: 'scatter', mode: 'markers', name: 'EF',
                    x: efPoints.map((p: any) => p.date),
                    y: efPoints.map((p: any) => p.efficiency_factor),
                    text: efPoints.map((p: any) => p.name),
                    marker: { color: '#4e91d4', size: 6, opacity: 0.5 },
                    hovertemplate: '<b>%{text}</b><br>%{x}<br>EF: %{y:.4f}<extra></extra>',
                  },
                  {
                    type: 'scatter', mode: 'lines', name: '30-day trend',
                    x: efPoints.map((p: any) => p.date),
                    y: efPoints.map((p: any) => p.smoothed_ef),
                    line: { color: '#2196F3', width: 2 },
                  },
                ]}
                layout={{
                  xaxis: { title: { text: 'Date' } },
                  yaxis: { title: { text: 'Efficiency Factor' } },
                }}
              />
          }
        </div>
      </section>

      <hr className="border-garmin-border" />

      {/* HR vs Sleep */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold text-white">HR vs Next-Night Sleep Score</h2>
        <p className="text-garmin-muted text-sm">
          Each point is one run paired with the sleep score the following night.
        </p>
        {sleepLoading ? <LoadingError loading /> : sleepError ? <LoadingError error={sleepError as Error} /> :
          sleepPoints.length === 0
            ? <LoadingError empty emptyMsg="No matching activity and sleep data in selected range." />
            : <Chart
                data={sleepTraces}
                layout={{
                  xaxis: { title: { text: 'HR (bpm, walk-removed)' } },
                  yaxis: { title: { text: 'Next-Night Sleep Score' } },
                }}
              />
        }
      </section>
    </div>
  )
}
