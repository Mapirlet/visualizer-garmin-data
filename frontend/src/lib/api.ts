import axios from 'axios'
import type { Filters } from './types'

const client = axios.create({ baseURL: '/api' })

function typesParam(types: string[]) {
  return types.length > 0 ? types.join(',') : undefined
}

export const api = {
  health: () => client.get('/health').then(r => r.data),

  // Activities
  dateRange: () => client.get('/activities/date-range').then(r => r.data),
  activityTypes: () => client.get('/activities/types').then(r => r.data),
  activities: (f: Filters) =>
    client.get('/activities', {
      params: { start: f.start, end: f.end, types: typesParam(f.types) },
    }).then(r => r.data),

  // HR vs Pace
  hrPace: (f: Filters) =>
    client.get('/hr-pace', {
      params: { start: f.start, end: f.end, types: typesParam(f.types) },
    }).then(r => r.data),
  efficiency: (f: Filters, paceMin: number, paceMax: number) =>
    client.get('/hr-pace/efficiency', {
      params: { start: f.start, end: f.end, types: typesParam(f.types), pace_min: paceMin, pace_max: paceMax },
    }).then(r => r.data),

  // HR vs Sleep
  hrSleep: (f: Filters) =>
    client.get('/hr-sleep', {
      params: { start: f.start, end: f.end, types: typesParam(f.types) },
    }).then(r => r.data),

  // Training load
  trainingLoad: (f: Filters) =>
    client.get('/training-load', {
      params: { start: f.start, end: f.end, types: typesParam(f.types) },
    }).then(r => r.data),

  // Sleep
  sleep: (period: string, offset: number, f: Filters) =>
    client.get('/sleep', {
      params: { period, offset, start: f.start, end: f.end },
    }).then(r => r.data),

  // Technique
  technique: (f: Filters) =>
    client.get('/technique', {
      params: { start: f.start, end: f.end, types: typesParam(f.types) },
    }).then(r => r.data),
  techniqueCorrelations: (f: Filters) =>
    client.get('/technique/correlations', {
      params: { start: f.start, end: f.end, types: typesParam(f.types) },
    }).then(r => r.data),
  techniqueScatter: (f: Filters, xMetric: string, yMetric: string) =>
    client.get('/technique/scatter', {
      params: { start: f.start, end: f.end, types: typesParam(f.types), x_metric: xMetric, y_metric: yMetric },
    }).then(r => r.data),

  // GPS
  gps: (f: Filters) =>
    client.get('/gps', {
      params: { start: f.start, end: f.end, types: typesParam(f.types) },
    }).then(r => r.data),

  // FIT
  fitActivities: (f: Filters) =>
    client.get('/fit/activities', {
      params: { start: f.start, end: f.end, types: typesParam(f.types) },
    }).then(r => r.data),
  fitDetail: (activityId: number) =>
    client.get(`/fit/${activityId}`).then(r => r.data),
  fitDecoupling: (activityId: number) =>
    client.get(`/fit/${activityId}/decoupling`).then(r => r.data),

  // Progress
  vo2max: (f: Filters) =>
    client.get('/progress/vo2max', {
      params: { start: f.start, end: f.end, types: typesParam(f.types) },
    }).then(r => r.data),
  paceAtHr: (f: Filters, hrMin: number, hrMax: number) =>
    client.get('/progress/pace-at-hr', {
      params: { start: f.start, end: f.end, types: typesParam(f.types), hr_min: hrMin, hr_max: hrMax },
    }).then(r => r.data),
  decouplingTrend: (f: Filters) =>
    client.get('/progress/decoupling', {
      params: { start: f.start, end: f.end, types: typesParam(f.types) },
    }).then(r => r.data),
  z2: (f: Filters, zones: number[]) =>
    client.get('/progress/z2', {
      params: { start: f.start, end: f.end, types: typesParam(f.types), zones: zones.join(',') },
    }).then(r => r.data),

  // Physio report
  physioReport: (injuryDate: string, weeksBack: number, types: string[], zones: number[]) =>
    client.get('/physio/report', {
      params: { injury_date: injuryDate, weeks_back: weeksBack, types: types.length ? types.join(',') : undefined, zones: zones.join(',') },
    }).then(r => r.data),

  // Export
  stats: (f: Filters) =>
    client.get('/export/stats', {
      params: { start: f.start, end: f.end, types: typesParam(f.types) },
    }).then(r => r.data),
  llmPrompt: (f: Filters, hrMax: number, hrLthr: number, hrRest: number) =>
    client.get('/export/llm-prompt', {
      params: { start: f.start, end: f.end, types: typesParam(f.types), hr_max: hrMax, hr_lthr: hrLthr, hr_rest: hrRest },
    }).then(r => r.data),
  monthlyCsvUrl: (f: Filters) => {
    const params = new URLSearchParams()
    if (f.start) params.set('start', f.start)
    if (f.end) params.set('end', f.end)
    if (f.types.length) params.set('types', f.types.join(','))
    return `/api/export/monthly-csv?${params}`
  },
}
