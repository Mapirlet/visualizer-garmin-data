import { create } from 'zustand'

interface FiltersState {
  start: string
  end: string
  types: string[]
  hrMax: number
  hrLthr: number
  hrRest: number
  // computed HR zones (Friel 5-zone from LTHR)
  hrZones: number[]
  setStart: (v: string) => void
  setEnd: (v: string) => void
  setTypes: (v: string[]) => void
  setHrMax: (v: number) => void
  setHrLthr: (v: number) => void
  setHrRest: (v: number) => void
}

function calcZones(lthr: number, hrMax: number): number[] {
  return [
    Math.floor(lthr * 0.85),
    Math.floor(lthr * 0.90),
    Math.floor(lthr * 0.95),
    Math.floor(lthr * 1.00),
    hrMax,
  ]
}

export const useFilters = create<FiltersState>((set, get) => ({
  start: '',
  end: '',
  types: [],
  hrMax: 212,
  hrLthr: 189,
  hrRest: 83,
  hrZones: calcZones(189, 212),

  setStart: (v) => set({ start: v }),
  setEnd: (v) => set({ end: v }),
  setTypes: (v) => set({ types: v }),
  setHrMax: (v) => set((s) => ({ hrMax: v, hrZones: calcZones(s.hrLthr, v) })),
  setHrLthr: (v) => set((s) => ({ hrLthr: v, hrZones: calcZones(v, s.hrMax) })),
  setHrRest: (v) => set({ hrRest: v }),
}))

export type { FiltersState }
