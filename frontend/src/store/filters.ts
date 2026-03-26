import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type ZoneMode = 'basic' | 'lthr' | 'custom'

// Returns [z1_hi, z2_hi, z3_hi, z4_hi] upper bounds
function calcBasicZones(hrMax: number): [number, number, number, number] {
  return [
    Math.floor(hrMax * 0.60),
    Math.floor(hrMax * 0.70),
    Math.floor(hrMax * 0.80),
    Math.floor(hrMax * 0.90),
  ]
}

function calcFrielZones(lthr: number): [number, number, number, number] {
  return [
    Math.floor(lthr * 0.81),
    Math.floor(lthr * 0.90),
    Math.floor(lthr * 1.00),
    Math.floor(lthr * 1.06),
  ]
}

interface FiltersState {
  start: string
  end: string
  types: string[]

  zoneMode: ZoneMode
  hrMax: number
  hrLthr: number
  hrRest: number
  // Custom zone upper bounds [z1_hi, z2_hi, z3_hi, z4_hi]
  customZones: [number, number, number, number]

  // Derived: the active zone bounds used everywhere
  hrZones: [number, number, number, number]

  setStart: (v: string) => void
  setEnd: (v: string) => void
  setTypes: (v: string[]) => void
  setZoneMode: (m: ZoneMode) => void
  setHrMax: (v: number) => void
  setHrLthr: (v: number) => void
  setHrRest: (v: number) => void
  setCustomZone: (index: number, v: number) => void
}

function deriveZones(mode: ZoneMode, hrMax: number, hrLthr: number, custom: [number,number,number,number]): [number,number,number,number] {
  if (mode === 'custom') return custom
  if (mode === 'lthr') return calcFrielZones(hrLthr)
  return calcBasicZones(hrMax)
}

export const useFilters = create<FiltersState>()(
  persist(
    (set) => ({
      start: '',
      end: '',
      types: [],
      zoneMode: 'lthr',
      hrMax: 212,
      hrLthr: 177,
      hrRest: 50,
      customZones: [168, 177, 196, 207],
      hrZones: calcFrielZones(177),

      setStart: (v) => set({ start: v }),
      setEnd: (v) => set({ end: v }),
      setTypes: (v) => set({ types: v }),
      setZoneMode: (m) => set((s) => ({
        zoneMode: m,
        hrZones: deriveZones(m, s.hrMax, s.hrLthr, s.customZones),
      })),
      setHrMax: (v) => set((s) => ({
        hrMax: v,
        hrZones: deriveZones(s.zoneMode, v, s.hrLthr, s.customZones),
      })),
      setHrLthr: (v) => set((s) => ({
        hrLthr: v,
        hrZones: deriveZones(s.zoneMode, s.hrMax, v, s.customZones),
      })),
      setHrRest: (v) => set({ hrRest: v }),
      setCustomZone: (i, v) => set((s) => {
        const z = [...s.customZones] as [number, number, number, number]
        z[i] = v
        const newCustom = z
        return {
          customZones: newCustom,
          hrZones: deriveZones(s.zoneMode, s.hrMax, s.hrLthr, newCustom),
        }
      }),
    }),
    { name: 'garmin-filters' }
  )
)

export type { FiltersState }
