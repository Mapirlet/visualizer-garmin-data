import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useFilters } from '../store/filters'
import { api } from '../lib/api'
import Chart from '../components/Chart'
import LoadingError from '../components/LoadingError'

const SEVERITY_STYLES: Record<string, string> = {
  warning: 'border-orange-500 bg-orange-500/10 text-orange-300',
  info:    'border-blue-500 bg-blue-500/10 text-blue-300',
  ok:      'border-green-600 bg-green-600/10 text-green-300',
}

const SEVERITY_ICON: Record<string, string> = {
  warning: '⚠',
  info:    'ℹ',
  ok:      '✓',
}

function injuryLine(injuryDate: string) {
  return {
    type: 'line' as const,
    x0: injuryDate, x1: injuryDate,
    y0: 0, y1: 1,
    yref: 'paper' as const,
    line: { color: '#ef4444', width: 2, dash: 'dash' as const },
  }
}

export default function PhysioReport() {
  const filters = useFilters()
  const today = new Date().toISOString().slice(0, 10)
  const [injuryDate, setInjuryDate] = useState(today)
  const [weeksBack, setWeeksBack] = useState(12)
  const [symptom, setSymptom] = useState('')

  const { data, isLoading, error } = useQuery({
    queryKey: ['physio-report', injuryDate, weeksBack, filters.types, filters.hrZones.join(',')],
    queryFn: () => api.physioReport(injuryDate, weeksBack, filters.types, filters.hrZones),
  })

  // ── Export text ─────────────────────────────────────────────────────────
  function buildExportText(): string {
    if (!data) return ''
    const lines = [
      `Physio Report generated ${today}`,
      `Injury / onset date: ${injuryDate}`,
      symptom ? `Symptom / area: ${symptom}` : null,
      `Analysis window: ${data.window_start} → ${injuryDate} (${weeksBack} weeks)`,
      '',
      '--- FLAGS ---',
      ...data.flags.map((f: { severity: string; category: string; message: string }) =>
        `[${f.severity.toUpperCase()}] ${f.category}: ${f.message}`
      ),
      '',
      '--- WEEKLY VOLUME ---',
      ...data.weekly_volume.map((r: { week: string; km: number; n_runs: number; elevation_m?: number }) =>
        `${r.week}: ${r.km} km over ${r.n_runs} run(s)${r.elevation_m != null ? `, ${Math.round(r.elevation_m)} m D+` : ''}`
      ),
      '',
      '--- WEEKLY INTENSITY (% time in zone) ---',
      ...data.weekly_intensity.map((r: { week: string; z1: number; z2: number; z3: number; z4: number; z5: number }) =>
        `${r.week}: Z1 ${r.z1}%  Z2 ${r.z2}%  Z3 ${r.z3}%  Z4 ${r.z4}%  Z5 ${r.z5}%`
      ),
      '',
      '--- WEEKLY SLEEP (avg score) ---',
      ...data.weekly_sleep.map((r: { week: string; avg_score: number }) =>
        `${r.week}: ${r.avg_score}`
      ),
    ].filter(l => l !== null)
    return lines.join('\n')
  }

  function copyToClipboard() {
    navigator.clipboard.writeText(buildExportText())
  }

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-xl font-semibold text-white">Physio Report</h2>
          <p className="text-garmin-muted text-sm mt-1">
            Context report for your physiotherapist — training load, intensity, and sleep in the weeks before an injury or pain onset.
          </p>
        </div>
        <button
          onClick={copyToClipboard}
          disabled={!data}
          className="px-4 py-2 text-sm rounded bg-garmin-blue text-white hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Copy for physio
        </button>
      </div>

      {/* ── Inputs ── */}
      <section className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div>
          <label className="block text-xs text-garmin-muted mb-1">Injury / onset date</label>
          <input
            type="date"
            value={injuryDate}
            onChange={e => setInjuryDate(e.target.value)}
            className="w-full bg-garmin-surface border border-garmin-border rounded px-3 py-2 text-sm text-garmin-text focus:outline-none focus:border-garmin-blue"
          />
        </div>
        <div>
          <label className="block text-xs text-garmin-muted mb-1">Lookback window</label>
          <select
            value={weeksBack}
            onChange={e => setWeeksBack(Number(e.target.value))}
            className="w-full bg-garmin-surface border border-garmin-border rounded px-3 py-2 text-sm text-garmin-text focus:outline-none focus:border-garmin-blue"
          >
            {[8, 12, 16, 24].map(w => (
              <option key={w} value={w}>{w} weeks</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-garmin-muted mb-1">Symptom / area (optional)</label>
          <input
            type="text"
            value={symptom}
            onChange={e => setSymptom(e.target.value)}
            placeholder="e.g. left Achilles tendinopathy"
            className="w-full bg-garmin-surface border border-garmin-border rounded px-3 py-2 text-sm text-garmin-text focus:outline-none focus:border-garmin-blue placeholder:text-garmin-muted/50"
          />
        </div>
      </section>

      {isLoading && <LoadingError loading />}
      {error && <LoadingError error={error as Error} />}

      {data && (
        <>
          {/* ── Flags ── */}
          <section>
            <h3 className="text-base font-medium text-white mb-3">Detected anomalies</h3>
            <div className="space-y-2">
              {data.flags.map((f: { severity: string; category: string; message: string }, i: number) => (
                <div
                  key={i}
                  className={`flex gap-3 items-start p-3 rounded border text-sm ${SEVERITY_STYLES[f.severity] ?? SEVERITY_STYLES.info}`}
                >
                  <span className="font-bold shrink-0">{SEVERITY_ICON[f.severity]}</span>
                  <div>
                    <span className="font-semibold">{f.category} </span>
                    {f.message}
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* ── Weekly volume ── */}
          {data.weekly_volume.length > 0 && (
            <section>
              <h3 className="text-base font-medium text-white mb-1">Weekly volume</h3>
              <p className="text-garmin-muted text-sm mb-3">
                Red dashed line marks the injury date. A sudden spike in the weeks before is a common injury predictor.
              </p>
              <Chart
                data={[
                  {
                    x: data.weekly_volume.map((r: { week: string }) => r.week),
                    y: data.weekly_volume.map((r: { km: number }) => r.km),
                    type: 'bar',
                    name: 'km/week',
                    marker: { color: '#1e88e5' },
                  },
                  ...(data.weekly_volume[0]?.elevation_m != null ? [{
                    x: data.weekly_volume.map((r: { week: string }) => r.week),
                    y: data.weekly_volume.map((r: { elevation_m?: number }) => r.elevation_m ?? 0),
                    type: 'bar' as const,
                    name: 'D+ (m)',
                    marker: { color: '#43a047' },
                    yaxis: 'y2',
                  }] : []),
                ]}
                layout={{
                  barmode: 'group',
                  shapes: [injuryLine(injuryDate)],
                  yaxis: { title: { text: 'km' } },
                  yaxis2: { title: { text: 'D+ (m)' }, overlaying: 'y', side: 'right', showgrid: false },
                }}
                height={280}
              />
            </section>
          )}

          {/* ── Weekly intensity ── */}
          {data.weekly_intensity.length > 0 && (
            <section>
              <h3 className="text-base font-medium text-white mb-1">Weekly intensity distribution</h3>
              <p className="text-garmin-muted text-sm mb-3">
                Friel zones from LTHR. High Z4/Z5 share without recovery weeks increases injury risk.
              </p>
              <Chart
                data={[
                  { x: data.weekly_intensity.map((r: { week: string }) => r.week), y: data.weekly_intensity.map((r: { z1: number }) => r.z1), type: 'bar', name: 'Z1 recovery', marker: { color: '#90caf9' } },
                  { x: data.weekly_intensity.map((r: { week: string }) => r.week), y: data.weekly_intensity.map((r: { z2: number }) => r.z2), type: 'bar', name: 'Z2 aerobic',  marker: { color: '#66bb6a' } },
                  { x: data.weekly_intensity.map((r: { week: string }) => r.week), y: data.weekly_intensity.map((r: { z3: number }) => r.z3), type: 'bar', name: 'Z3 tempo',    marker: { color: '#ffa726' } },
                  { x: data.weekly_intensity.map((r: { week: string }) => r.week), y: data.weekly_intensity.map((r: { z4: number }) => r.z4), type: 'bar', name: 'Z4 threshold',marker: { color: '#ef5350' } },
                  { x: data.weekly_intensity.map((r: { week: string }) => r.week), y: data.weekly_intensity.map((r: { z5: number }) => r.z5), type: 'bar', name: 'Z5 max',      marker: { color: '#b71c1c' } },
                ]}
                layout={{
                  barmode: 'stack',
                  shapes: [injuryLine(injuryDate)],
                  yaxis: { title: { text: '% time' } },
                }}
                height={280}
              />
            </section>
          )}

          {/* ── Sleep ── */}
          {data.weekly_sleep.length > 0 && (
            <section>
              <h3 className="text-base font-medium text-white mb-1">Weekly sleep score</h3>
              <p className="text-garmin-muted text-sm mb-3">
                Sustained poor sleep impairs recovery and raises injury risk. A drop in the weeks before onset is a meaningful signal.
              </p>
              <Chart
                data={[{
                  x: data.weekly_sleep.map((r: { week: string }) => r.week),
                  y: data.weekly_sleep.map((r: { avg_score: number }) => r.avg_score),
                  type: 'scatter',
                  mode: 'lines+markers',
                  name: 'Avg sleep score',
                  line: { color: '#8e24aa' },
                  marker: { color: '#8e24aa' },
                }]}
                layout={{
                  shapes: [injuryLine(injuryDate)],
                  yaxis: { title: { text: 'Sleep score' }, range: [0, 100] },
                }}
                height={240}
              />
            </section>
          )}

          {/* ── Aerobic decoupling ── */}
          {data.decoupling.length > 0 && (
            <section>
              <h3 className="text-base font-medium text-white mb-1">Aerobic decoupling</h3>
              <p className="text-garmin-muted text-sm mb-3">
                Rising decoupling over several weeks signals accumulated fatigue. Values above 5% suggest the body is under stress.
              </p>
              <Chart
                data={[{
                  x: data.decoupling.map((r: { date: string }) => r.date),
                  y: data.decoupling.map((r: { aerobic_decoupling: number }) => r.aerobic_decoupling),
                  type: 'scatter',
                  mode: 'lines+markers',
                  name: 'Decoupling %',
                  line: { color: '#ffa726' },
                  marker: { color: '#ffa726' },
                  text: data.decoupling.map((r: { name: string }) => r.name),
                  hovertemplate: '%{text}<br>%{y:.1f}%<extra></extra>',
                }]}
                layout={{
                  shapes: [
                    injuryLine(injuryDate),
                    { type: 'line', x0: data.decoupling[0]?.date, x1: injuryDate, y0: 5, y1: 5, line: { color: '#ef4444', width: 1, dash: 'dot' } },
                  ],
                  yaxis: { title: { text: 'Decoupling %' } },
                }}
                height={240}
              />
            </section>
          )}

          {/* ── Export block ── */}
          <section>
            <h3 className="text-base font-medium text-white mb-2">Export for your physio</h3>
            <p className="text-garmin-muted text-sm mb-3">
              Copy this text and share it directly, or paste it into an AI assistant to answer follow-up questions.
            </p>
            <pre className="bg-garmin-surface border border-garmin-border rounded p-4 text-xs text-garmin-text whitespace-pre-wrap overflow-auto max-h-64">
              {buildExportText()}
            </pre>
            <button
              onClick={copyToClipboard}
              className="mt-3 px-4 py-2 text-sm rounded bg-garmin-blue text-white hover:bg-blue-500"
            >
              Copy to clipboard
            </button>
          </section>
        </>
      )}
    </div>
  )
}
