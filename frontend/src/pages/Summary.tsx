import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useFilters } from '../store/filters'
import { api } from '../lib/api'
import LoadingError from '../components/LoadingError'

type Period = 'week' | 'month' | 'year' | 'all'

function fmtPace(v: number | null) {
  if (!v) return '-'
  const m = Math.floor(v)
  const s = Math.round((v - m) * 60).toString().padStart(2, '0')
  return `${m}:${s}`
}

export default function Summary() {
  const filters = useFilters()
  const [period, setPeriod] = useState<Period>('all')
  const [offset, setOffset] = useState(0)
  const [llmText, setLlmText] = useState('')

  const handlePeriod = (p: Period) => { setPeriod(p); setOffset(0) }

  const { data: actsData, isLoading: actsLoading } = useQuery({
    queryKey: ['activities-all', filters.start, filters.end, filters.types],
    queryFn: () => api.activities(filters),
    enabled: !!filters.start,
  })

  const { data: statsData, isLoading: statsLoading } = useQuery({
    queryKey: ['stats', filters.start, filters.end, filters.types],
    queryFn: () => api.stats(filters),
    enabled: !!filters.start,
  })

  const { data: llmData, isLoading: llmLoading } = useQuery({
    queryKey: ['llm-prompt', filters.start, filters.end, filters.types, filters.hrMax, filters.hrLthr, filters.hrRest],
    queryFn: () => api.llmPrompt(filters, filters.hrMax, filters.hrLthr, filters.hrRest),
    enabled: !!filters.start,
  })

  const allActs = actsData?.activities ?? []

  // Period filter
  const today = new Date()
  const filtered = allActs.filter((a: any) => {
    if (period === 'all') return true
    const d = new Date(a.date)
    if (period === 'week') {
      const start = new Date(today)
      start.setDate(today.getDate() - today.getDay() + offset * 7)
      const end = new Date(start); end.setDate(start.getDate() + 6)
      return d >= start && d <= end
    }
    if (period === 'month') {
      const ref = new Date(today.getFullYear(), today.getMonth() + offset, 1)
      return d.getFullYear() === ref.getFullYear() && d.getMonth() === ref.getMonth()
    }
    if (period === 'year') {
      return d.getFullYear() === today.getFullYear() + offset
    }
    return true
  }).sort((a: any, b: any) => b.date.localeCompare(a.date))

  const periodLabel = (() => {
    if (period === 'all') return 'All time'
    if (period === 'week') {
      const start = new Date(today); start.setDate(today.getDate() - today.getDay() + offset * 7)
      const end = new Date(start); end.setDate(start.getDate() + 6)
      return `${start.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })} to ${end.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}`
    }
    if (period === 'month') {
      const ref = new Date(today.getFullYear(), today.getMonth() + offset, 1)
      return ref.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })
    }
    if (period === 'year') return String(today.getFullYear() + offset)
    return ''
  })()

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-white">Summary</h2>

      {/* Activity log */}
      <section>
        <h3 className="text-base font-medium text-white mb-3">Activity Log</h3>

        <div className="flex items-center gap-2 flex-wrap mb-3">
          {(['week', 'month', 'year', 'all'] as Period[]).map(p => (
            <button key={p} onClick={() => handlePeriod(p)}
              className={`px-3 py-1 rounded text-sm font-medium transition-colors ${period === p ? 'bg-garmin-blue text-white' : 'bg-garmin-surface text-garmin-muted hover:text-white'}`}>
              {p.charAt(0).toUpperCase() + p.slice(1)}
            </button>
          ))}
          {period !== 'all' && (
            <div className="flex items-center gap-2 ml-4">
              <button onClick={() => setOffset(o => o - 1)}
                className="w-7 h-7 flex items-center justify-center bg-garmin-surface hover:bg-garmin-border rounded text-white">←</button>
              <span className="text-sm text-white min-w-[160px] text-center">{periodLabel}</span>
              <button onClick={() => setOffset(o => o + 1)} disabled={offset >= 0}
                className="w-7 h-7 flex items-center justify-center bg-garmin-surface hover:bg-garmin-border rounded text-white disabled:opacity-30 disabled:cursor-not-allowed">→</button>
            </div>
          )}
          {period === 'all' && <span className="ml-4 text-sm text-garmin-muted">{periodLabel}</span>}
        </div>

        {actsLoading ? <LoadingError loading /> : filtered.length === 0 ? (
          <LoadingError empty emptyMsg="No activities in this period." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-garmin-border text-garmin-muted text-left">
                  {['Date', 'Type', 'Name', 'Dist (km)', 'Pace', 'HR', 'Load', 'VO2max'].map(h => (
                    <th key={h} className="pb-2 pr-4 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((a: any) => (
                  <tr key={a.activity_id} className="border-b border-garmin-border/50 hover:bg-garmin-surface/50 transition-colors">
                    <td className="py-2 pr-4 text-garmin-muted">{a.date}</td>
                    <td className="py-2 pr-4">{a.activity_type}</td>
                    <td className="py-2 pr-4 max-w-[180px] truncate" title={a.name}>{a.name}</td>
                    <td className="py-2 pr-4">{a.distance_km?.toFixed(1) ?? '-'}</td>
                    <td className="py-2 pr-4">{fmtPace(a.avg_pace_min_km)}</td>
                    <td className="py-2 pr-4">{a.avg_hr?.toFixed(0) ?? '-'}</td>
                    <td className="py-2 pr-4">{a.training_load?.toFixed(0) ?? '-'}</td>
                    <td className="py-2 pr-4">{a.vo2max?.toFixed(1) ?? '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Overall stats */}
      <section>
        <h3 className="text-base font-medium text-white mb-3">Overall Statistics</h3>
        {statsLoading ? <LoadingError loading /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-garmin-border text-garmin-muted text-left">
                  {['Metric', 'Mean', 'Median', 'Std', 'Best', 'Worst', 'N'].map(h => (
                    <th key={h} className="pb-2 pr-4 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(statsData?.overall ?? []).map((r: any) => (
                  <tr key={r.metric} className="border-b border-garmin-border/50">
                    <td className="py-2 pr-4 text-white font-medium">{r.metric}</td>
                    <td className="py-2 pr-4 text-garmin-muted">{r.mean}</td>
                    <td className="py-2 pr-4 text-garmin-muted">{r.median}</td>
                    <td className="py-2 pr-4 text-garmin-muted">{r.std}</td>
                    <td className="py-2 pr-4 text-green-400">{r.best}</td>
                    <td className="py-2 pr-4 text-red-400">{r.worst}</td>
                    <td className="py-2 pr-4 text-garmin-muted">{r.n}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Monthly breakdown */}
      {(statsData?.monthly ?? []).length > 0 && (
        <section>
          <h3 className="text-base font-medium text-white mb-3">Monthly Breakdown</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-garmin-border text-garmin-muted text-left">
                  {Object.keys(statsData.monthly[0]).map(k => (
                    <th key={k} className="pb-2 pr-4 font-medium">{k}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {statsData.monthly.map((r: any, i: number) => (
                  <tr key={i} className="border-b border-garmin-border/50">
                    {Object.values(r).map((v: any, j) => (
                      <td key={j} className="py-2 pr-4 text-garmin-text">
                        {typeof v === 'number' ? v.toFixed(2) : (v ?? '-')}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <a
            href={api.monthlyCsvUrl(filters)}
            download="garmin_monthly.csv"
            className="inline-block mt-3 px-4 py-2 bg-garmin-blue hover:bg-blue-600 text-white text-sm rounded transition-colors"
          >
            Download monthly CSV
          </a>
        </section>
      )}

      {/* LLM export */}
      <section>
        <h3 className="text-base font-medium text-white mb-3">LLM Prompt</h3>
        <p className="text-garmin-muted text-sm mb-3">
          Copy this into ChatGPT or Claude for analysis of your training data.
        </p>
        {llmLoading ? <LoadingError loading /> : (
          <textarea
            readOnly
            value={llmData?.text ?? ''}
            rows={14}
            className="w-full bg-garmin-surface border border-garmin-border rounded p-3 text-xs text-garmin-text font-mono focus:outline-none focus:border-garmin-blue resize-y"
          />
        )}
        {llmData?.text && (
          <button
            onClick={() => navigator.clipboard.writeText(llmData.text)}
            className="mt-2 px-4 py-2 bg-garmin-surface hover:bg-garmin-border text-garmin-text text-sm rounded transition-colors"
          >
            Copy to clipboard
          </button>
        )}
      </section>
    </div>
  )
}
