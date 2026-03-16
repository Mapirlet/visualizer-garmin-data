import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useFilters } from '../store/filters'
import { api } from '../lib/api'
import Chart from '../components/Chart'
import LoadingError from '../components/LoadingError'

type Period = 'week' | 'month' | 'year' | 'all'

export default function SleepTrends() {
  const filters = useFilters()
  const [period, setPeriod] = useState<Period>('all')
  const [offset, setOffset] = useState(0)

  // Reset offset when period changes
  const handlePeriod = (p: Period) => {
    setPeriod(p)
    setOffset(0)
  }

  const { data, isLoading, error } = useQuery({
    queryKey: ['sleep', period, offset, filters.start, filters.end],
    queryFn: () => api.sleep(period, offset, filters),
    enabled: !!filters.start,
  })

  if (isLoading) return <LoadingError loading />
  if (error) return <LoadingError error={error as Error} />

  const rows = data?.rows ?? []
  const label = data?.label ?? ''

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold text-white">Sleep Trends</h2>

      <div className="flex items-center gap-2 flex-wrap">
        {(['week', 'month', 'year', 'all'] as Period[]).map(p => (
          <button
            key={p}
            onClick={() => handlePeriod(p)}
            className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
              period === p
                ? 'bg-garmin-blue text-white'
                : 'bg-garmin-surface text-garmin-muted hover:text-white'
            }`}
          >
            {p.charAt(0).toUpperCase() + p.slice(1)}
          </button>
        ))}

        {period !== 'all' && (
          <div className="flex items-center gap-2 ml-4">
            <button
              onClick={() => setOffset(o => o - 1)}
              className="w-7 h-7 flex items-center justify-center bg-garmin-surface hover:bg-garmin-border rounded text-white transition-colors"
            >
              ←
            </button>
            <span className="text-sm text-white min-w-[140px] text-center">{label}</span>
            <button
              onClick={() => setOffset(o => o + 1)}
              disabled={offset >= 0}
              className="w-7 h-7 flex items-center justify-center bg-garmin-surface hover:bg-garmin-border rounded text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            >
              →
            </button>
          </div>
        )}
        {period === 'all' && <span className="ml-4 text-sm text-garmin-muted">{label}</span>}
      </div>

      {rows.length === 0 ? (
        <LoadingError empty emptyMsg="No sleep data in this period." />
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <Chart
            title="Sleep Score Over Time"
            data={[{
              type: 'bar',
              x: rows.map((r: any) => r.date),
              y: rows.map((r: any) => r.overall_score),
              marker: { color: '#4e91d4' },
              hovertemplate: '%{x}<br>Score: %{y}<extra></extra>',
            }]}
            layout={{ xaxis: { title: { text: 'Date' } }, yaxis: { title: { text: 'Sleep Score' } } }}
          />

          <div>
            <Chart
              title="Sleep Stage Breakdown"
              data={[
                {
                  type: 'bar',
                  name: 'Deep',
                  x: rows.map((r: any) => r.date),
                  y: rows.map((r: any) => r.deep_min),
                  marker: { color: '#1a3a5c' },
                  hovertemplate: '%{x}<br>Deep: %{y:.0f} min<extra></extra>',
                },
                {
                  type: 'bar',
                  name: 'REM',
                  x: rows.map((r: any) => r.date),
                  y: rows.map((r: any) => r.rem_min),
                  marker: { color: '#4e91d4' },
                  hovertemplate: '%{x}<br>REM: %{y:.0f} min<extra></extra>',
                },
                {
                  type: 'bar',
                  name: 'Light',
                  x: rows.map((r: any) => r.date),
                  y: rows.map((r: any) => r.light_min),
                  marker: { color: '#aed4f5' },
                  hovertemplate: '%{x}<br>Light: %{y:.0f} min<extra></extra>',
                },
              ]}
              layout={{
                barmode: 'stack',
                xaxis: { title: { text: 'Date' } },
                yaxis: { title: { text: 'Minutes' } },
              }}
            />
            <p className="text-garmin-muted text-xs mt-2 leading-relaxed">
              <strong className="text-white">Deep</strong> (dark blue) is the most restorative stage focused on physical recovery,
              muscle repair and immune function. Adults need around 1 to 2 hours per night.{' '}
              <strong className="text-white">REM</strong> (medium blue) is where dreaming happens and where the brain consolidates
              memories, learning and mood. Around 90 minutes per night is ideal.{' '}
              <strong className="text-white">Light</strong> (light blue) is the transitional stage between the other two.
              It is necessary but the least restorative of the three.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
