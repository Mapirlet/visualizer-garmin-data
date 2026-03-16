import { NavLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useFilters } from '../store/filters'
import { api } from '../lib/api'

const NAV = [
  { to: '/activity',     label: 'Activity Detail' },
  { to: '/technique',    label: 'Technique' },
  { to: '/progress',     label: 'Progress' },
  { to: '/hr-analysis',  label: 'HR Analysis' },
  { to: '/training-load',label: 'Training Load' },
  { to: '/sleep',        label: 'Sleep Trends' },
  { to: '/routes',       label: 'Routes' },
  { to: '/summary',      label: 'Summary' },
]

export default function Sidebar() {
  const {
    start, end, types,
    hrMax, hrLthr, hrRest,
    hrZones,
    setStart, setEnd, setTypes,
    setHrMax, setHrLthr, setHrRest,
  } = useFilters()

  const { data: typesData } = useQuery({
    queryKey: ['activity-types'],
    queryFn: api.activityTypes,
  })
  const allTypes: string[] = typesData?.types ?? []

  return (
    <aside className="w-60 min-h-screen bg-garmin-sidebar border-r border-garmin-border flex flex-col">
      <div className="p-4 border-b border-garmin-border">
        <h1 className="text-white font-bold text-base leading-tight">Garmin Data<br />Visualizer</h1>
      </div>

      <nav className="py-2">
        {NAV.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `block px-4 py-2 text-sm transition-colors ${
                isActive
                  ? 'bg-garmin-blue/20 text-white border-l-2 border-garmin-blue'
                  : 'text-garmin-muted hover:text-white hover:bg-white/5'
              }`
            }
          >
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="mt-auto p-4 space-y-4 border-t border-garmin-border text-sm">
        <div>
          <p className="text-garmin-muted text-xs font-medium uppercase tracking-wider mb-2">Date range</p>
          <div className="space-y-1">
            <input
              type="date"
              value={start}
              onChange={e => setStart(e.target.value)}
              className="w-full bg-garmin-surface border border-garmin-border rounded px-2 py-1 text-xs text-garmin-text focus:outline-none focus:border-garmin-blue"
            />
            <input
              type="date"
              value={end}
              onChange={e => setEnd(e.target.value)}
              className="w-full bg-garmin-surface border border-garmin-border rounded px-2 py-1 text-xs text-garmin-text focus:outline-none focus:border-garmin-blue"
            />
          </div>
        </div>

        <div>
          <p className="text-garmin-muted text-xs font-medium uppercase tracking-wider mb-2">Activity types</p>
          <div className="space-y-1 max-h-32 overflow-y-auto">
            {allTypes.map(t => (
              <label key={t} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={types.includes(t)}
                  onChange={e => {
                    if (e.target.checked) setTypes([...types, t])
                    else setTypes(types.filter(x => x !== t))
                  }}
                  className="rounded border-garmin-border"
                />
                <span className="text-xs text-garmin-text">{t}</span>
              </label>
            ))}
          </div>
        </div>

        <div>
          <p className="text-garmin-muted text-xs font-medium uppercase tracking-wider mb-2">HR Zones (Friel)</p>
          <div className="space-y-1">
            {[
              { label: 'Max HR', value: hrMax, set: setHrMax },
              { label: 'LTHR', value: hrLthr, set: setHrLthr },
              { label: 'Resting HR', value: hrRest, set: setHrRest },
            ].map(({ label, value, set }) => (
              <div key={label} className="flex items-center justify-between gap-2">
                <span className="text-xs text-garmin-muted">{label}</span>
                <input
                  type="number"
                  value={value}
                  onChange={e => set(Number(e.target.value))}
                  className="w-16 bg-garmin-surface border border-garmin-border rounded px-2 py-0.5 text-xs text-garmin-text text-right focus:outline-none focus:border-garmin-blue"
                />
              </div>
            ))}
          </div>
          <p className="text-garmin-muted text-xs mt-2">
            Z2 {hrZones[0]}–{hrZones[1]} bpm
          </p>
        </div>
      </div>
    </aside>
  )
}
