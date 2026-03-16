export interface Activity {
  activity_id: number
  date: string
  name: string
  activity_type: string
  distance_km: number
  duration_min: number
  avg_hr: number | null
  max_hr: number | null
  avg_pace_min_km: number | null
  calories: number | null
  vo2max: number | null
  aerobic_te: number | null
  anaerobic_te: number | null
  training_load: number | null
  avg_power: number | null
  label?: string
}

export interface SleepRow {
  date: string
  overall_score: number | null
  quality_score: number | null
  duration_score: number | null
  deep_min: number | null
  light_min: number | null
  rem_min: number | null
  awake_min: number | null
  total_sleep_min: number | null
  avg_stress: number | null
  avg_respiration: number | null
  awake_count: number | null
}

export interface TechniqueRow {
  date: string
  activity_id: number
  name: string
  activity_type: string
  avg_hr: number | null
  avg_pace_min_km: number | null
  avg_cadence: number | null
  avg_vertical_oscillation: number | null
  avg_ground_contact_time: number | null
  avg_stride_length: number | null
  avg_vertical_ratio: number | null
  run_ratio: number | null
  aerobic_decoupling: number | null
  pct_z1: number | null
  pct_z2: number | null
  pct_z3: number | null
  pct_z4: number | null
  pct_z5: number | null
}

export interface FitRecord {
  distance_km: number | null
  heart_rate: number | null
  pace: number | null
  gap: number | null
  altitude: number | null
  grade_pct: number | null
  cadence_spm: number | null
  vertical_oscillation: number | null
  ground_contact_time: number | null
  vertical_ratio: number | null
  stride_length: number | null
  is_walking: boolean
  cadence_spm_zone?: string
  vertical_oscillation_zone?: string
  ground_contact_time_zone?: string
  vertical_ratio_zone?: string
  lat?: number
  lon?: number
}

export interface OlsTrendline {
  slope: number
  intercept: number
  r2: number
  x: [number, number]
  y: [number, number]
}

export interface Filters {
  start: string
  end: string
  types: string[]
  hrMax: number
  hrLthr: number
  hrRest: number
}
