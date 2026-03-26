import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useFilters } from '../store/filters'
import { api } from '../lib/api'
import Chart from '../components/Chart'
import LoadingError from '../components/LoadingError'

const ZONE_COLORS: Record<string, string> = {
  'Z1 recovery': '#90caf9',
  'Z2 aerobic': '#66bb6a',
  'Z3 tempo': '#ffa726',
  'Z4 threshold': '#ef5350',
  'Z5 max': '#b71c1c',
}

export default function Progress() {
  const filters = useFilters()
  const [hrBand, setHrBand] = useState<[number, number]>([filters.hrZones[0], filters.hrZones[1]])

  const { data: vo2Data, isLoading: vo2Loading } = useQuery({
    queryKey: ['vo2max', filters.start, filters.end, filters.types],
    queryFn: () => api.vo2max(filters),
    enabled: !!filters.start,
  })

  const { data: paceData, isLoading: paceLoading } = useQuery({
    queryKey: ['pace-at-hr', filters.start, filters.end, filters.types, hrBand[0], hrBand[1]],
    queryFn: () => api.paceAtHr(filters, hrBand[0], hrBand[1]),
    enabled: !!filters.start,
  })

  const { data: decData, isLoading: decLoading } = useQuery({
    queryKey: ['decoupling', filters.start, filters.end, filters.types],
    queryFn: () => api.decouplingTrend(filters),
    enabled: !!filters.start,
  })

  const z2Lo = filters.hrZones[0]
  const z2Hi = filters.hrZones[1]

  const { data: z2Data, isLoading: z2Loading } = useQuery({
    queryKey: ['z2', filters.start, filters.end, filters.types, filters.hrZones.join(',')],
    queryFn: () => api.z2(filters, filters.hrZones),
    enabled: !!filters.start,
  })

  return (
    <div className="space-y-8">
      <h2 className="text-xl font-semibold text-white">Fitness Progress</h2>

      {/* VO2max */}
      <section>
        <h3 className="text-base font-medium text-white mb-1">VO2max Over Time</h3>
        <p className="text-garmin-muted text-sm mb-3">
          Garmin estimated VO2max from running activities. Upward trend means improving aerobic fitness.
        </p>
        {vo2Loading ? <LoadingError loading /> : (
          (vo2Data?.points ?? []).length === 0
            ? <LoadingError empty emptyMsg="No VO2max data in selected range." />
            : <Chart
                data={[
                  {
                    type: 'scatter', mode: 'markers', name: 'VO2max',
                    x: vo2Data.points.map((p: any) => p.date),
                    y: vo2Data.points.map((p: any) => p.vo2max),
                    text: vo2Data.points.map((p: any) => p.name),
                    marker: { color: '#4e91d4', size: 7, opacity: 0.5 },
                    hovertemplate: '<b>%{text}</b><br>%{x}<br>VO2max: %{y:.1f}<extra></extra>',
                  },
                  {
                    type: 'scatter', mode: 'lines', name: '30-day trend',
                    x: vo2Data.points.map((p: any) => p.date),
                    y: vo2Data.points.map((p: any) => p.smoothed),
                    line: { color: '#2196F3', width: 2 },
                  },
                ]}
                layout={{ xaxis: { title: { text: 'Date' } }, yaxis: { title: { text: 'VO2max (ml/kg/min)' } } }}
              />
        )}
      </section>

      {/* Pace at fixed HR */}
      <section>
        <h3 className="text-base font-medium text-white mb-1">Pace at Fixed HR</h3>
        <p className="text-garmin-muted text-sm mb-3">
          Filter to a narrow HR band so effort is constant. If pace improves at the same HR, you are getting fitter.
          Uses grade-adjusted pace (GAP) when altitude data is available so trail runs compare fairly against flat runs.
        </p>
        {!paceData?.has_data ? (
          <LoadingError cacheMsg="uv run python -m src.cache" />
        ) : (
          <>
            <div className="flex gap-4 items-center mb-3 text-sm">
              <label className="text-garmin-muted">HR band</label>
              <input type="number" value={hrBand[0]} min={100} max={hrBand[1] - 1}
                onChange={e => setHrBand([Number(e.target.value), hrBand[1]])}
                className="w-16 bg-garmin-surface border border-garmin-border rounded px-2 py-1 text-garmin-text focus:outline-none focus:border-garmin-blue" />
              <span className="text-garmin-muted">to</span>
              <input type="number" value={hrBand[1]} min={hrBand[0] + 1} max={220}
                onChange={e => setHrBand([hrBand[0], Number(e.target.value)])}
                className="w-16 bg-garmin-surface border border-garmin-border rounded px-2 py-1 text-garmin-text focus:outline-none focus:border-garmin-blue" />
              <span className="text-garmin-muted">bpm</span>
            </div>
            {paceLoading ? <LoadingError loading /> : (
              (paceData?.points ?? []).length === 0
                ? <LoadingError empty emptyMsg="Not enough runs in this HR band. Widen the range." />
                : <Chart
                    data={[
                      {
                        type: 'scatter', mode: 'markers', name: paceData.pace_label ?? 'Pace',
                        x: paceData.points.map((p: any) => p.date),
                        y: paceData.points.map((p: any) => p.pace_display),
                        marker: { color: '#4e91d4', size: 6, opacity: 0.5 },
                        hovertemplate: `%{x}<br>${paceData.pace_label ?? 'Pace'}: %{y:.2f} min/km<br>HR: %{customdata} bpm<extra></extra>`,
                        customdata: paceData.points.map((p: any) => p.avg_hr),
                      },
                      {
                        type: 'scatter', mode: 'lines', name: '60-day trend',
                        x: paceData.points.map((p: any) => p.date),
                        y: paceData.points.map((p: any) => p.smoothed_pace),
                        line: { color: '#e53935', width: 2 },
                      },
                    ]}
                    layout={{
                      xaxis: { title: { text: 'Date' } },
                      yaxis: { title: { text: paceData.pace_label ?? 'Pace (min/km)' }, autorange: 'reversed' },
                    }}
                  />
            )}
          </>
        )}
      </section>

      {/* Aerobic decoupling trend */}
      <section>
        <h3 className="text-base font-medium text-white mb-1">Aerobic Decoupling Over Time</h3>
        <p className="text-garmin-muted text-sm mb-3">
          Aerobic decoupling measures cardiac drift, meaning how much your HR rises relative to pace as a run progresses.
          It compares Efficiency Factor (pace ÷ HR) in the first half vs the second half.
          A downward trend over weeks means your heart is drifting less at the same effort. Your aerobic base is building.
          Green line is the 5% threshold (solid base). Red line is 10% (aerobically taxed). Uses GAP so trail elevation doesn't distort the result.
        </p>
        {decLoading ? <LoadingError loading /> : !decData?.has_data ? (
          <LoadingError cacheMsg="uv run python -m src.cache" />
        ) : (decData?.points ?? []).length === 0 ? (
          <LoadingError empty />
        ) : (
          <Chart
            data={[
              {
                type: 'scatter', mode: 'markers', name: 'Decoupling',
                x: decData.points.map((p: any) => p.date),
                y: decData.points.map((p: any) => p.aerobic_decoupling),
                marker: { color: '#4e91d4', size: 6, opacity: 0.5 },
                hovertemplate: '%{x}<br>Decoupling: %{y:.1f}%<extra></extra>',
              },
              {
                type: 'scatter', mode: 'lines', name: '60-day trend',
                x: decData.points.map((p: any) => p.date),
                y: decData.points.map((p: any) => p.smoothed),
                line: { color: '#333', width: 2 },
              },
            ]}
            layout={{
              xaxis: { title: { text: 'Date' } },
              yaxis: { title: { text: 'Decoupling (%)' } },
              shapes: [
                { type: 'line', x0: 0, x1: 1, xref: 'paper', y0: 5, y1: 5, line: { color: '#43a047', dash: 'dash', width: 1 } },
                { type: 'line', x0: 0, x1: 1, xref: 'paper', y0: 10, y1: 10, line: { color: '#e53935', dash: 'dash', width: 1 } },
              ],
              annotations: [
                { x: 1, xref: 'paper', y: 5, text: '5% good', showarrow: false, xanchor: 'right', font: { color: '#43a047', size: 11 } },
                { x: 1, xref: 'paper', y: 10, text: '10% poor', showarrow: false, xanchor: 'right', font: { color: '#e53935', size: 11 } },
              ],
            } as any}
          />
        )}
      </section>

      {/* Z2 fitness tracker */}
      <section>
        <h3 className="text-base font-medium text-white mb-1">Z2 Fitness Tracker</h3>
        <p className="text-garmin-muted text-sm mb-3">
          Your Z2 is {z2Lo} to {z2Hi} bpm. At the same low HR, are you running faster over time? More mitochondria and better fat oxidation means same effort, faster pace.
        </p>
        {z2Loading ? <LoadingError loading /> : !z2Data?.has_data ? (
          <LoadingError cacheMsg="uv run python -m src.cache" />
        ) : (
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <div>
              <p className="text-sm text-white mb-2">Efficiency Factor in Z2 (HR {z2Lo} to {z2Hi} bpm)</p>
              {(z2Data?.ef_points ?? []).length === 0 ? (
                <LoadingError empty emptyMsg={`Not enough runs with avg HR in Z2 (${z2Lo} to ${z2Hi}).`} />
              ) : (
                <Chart
                  data={[
                    {
                      type: 'scatter', mode: 'markers', name: 'EF',
                      x: z2Data.ef_points.map((p: any) => p.date),
                      y: z2Data.ef_points.map((p: any) => p.ef),
                      marker: { color: '#4e91d4', size: 6, opacity: 0.5 },
                    },
                    {
                      type: 'scatter', mode: 'lines', name: '60-day trend',
                      x: z2Data.ef_points.map((p: any) => p.date),
                      y: z2Data.ef_points.map((p: any) => p.smoothed_ef),
                      line: { color: '#1565c0', width: 2 },
                    },
                  ]}
                  height={280}
                  layout={{ xaxis: { title: { text: 'Date' } }, yaxis: { title: { text: 'Efficiency Factor' } } }}
                />
              )}
            </div>
            <div>
              <p className="text-sm text-white mb-2">HR zone distribution per month</p>
              {(z2Data?.zone_dist ?? []).length === 0 ? (
                <LoadingError empty />
              ) : (() => {
                const zoneLabels = ['Z1 recovery', 'Z2 aerobic', 'Z3 tempo', 'Z4 threshold', 'Z5 max']
                return (
                  <Chart
                    data={zoneLabels.map(zone => ({
                      type: 'bar' as const,
                      name: zone,
                      x: z2Data.zone_dist.filter((r: any) => r.zone_label === zone).map((r: any) => r.month),
                      y: z2Data.zone_dist.filter((r: any) => r.zone_label === zone).map((r: any) => r.pct),
                      marker: { color: ZONE_COLORS[zone] },
                    }))}
                    height={280}
                    layout={{ barmode: 'stack', xaxis: { title: { text: 'Month' } }, yaxis: { title: { text: '% of runs' } } }}
                  />
                )
              })()}
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
