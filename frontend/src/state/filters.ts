import type { Category, Hotspot, RiskBand } from '../api/schema'
export type SortField = 'acq_date' | 'risk_score' | 'frp' | 'persistence_count_30d'
export interface Filters {
  predicted_class: Category | ''; risk_band: RiskBand | ''; day_night: 'D' | 'N' | '';
  date_from: string; date_to: string; min_frp: string; max_frp: string;
  min_risk_score: string; max_risk_score: string; min_persistence: string; max_persistence: string;
  west: string; south: string; east: string; north: string;
}
export const EMPTY_FILTERS: Filters = {
  predicted_class: '', risk_band: '', day_night: '', date_from: '', date_to: '',
  min_frp: '', max_frp: '', min_risk_score: '', max_risk_score: '',
  min_persistence: '', max_persistence: '', west: '', south: '', east: '', north: '',
}
export interface QueryState { filters: Filters; sort: SortField; order: 'asc' | 'desc' }
export const INITIAL_QUERY: QueryState = { filters: EMPTY_FILTERS, sort: 'acq_date', order: 'asc' }
export function activeFilterCount(f: Filters) {
  return Object.entries(f).filter(([k, v]) => v !== '' && !['west', 'south', 'east', 'north'].includes(k)).length +
    (['west', 'south', 'east', 'north'].some(k => f[k as keyof Filters] !== '') ? 1 : 0)
}
export function validateFilters(f: Filters): string | null {
  for (const k of ['date_from', 'date_to'] as const) {
    if (f[k] && (!/^\d{4}-\d{2}-\d{2}$/.test(f[k]) || Number.isNaN(Date.parse(f[k])) ||
      new Date(f[k]).toISOString().slice(0, 10) !== f[k])) return 'Enter valid acquisition dates.'
  }
  if (f.date_from && f.date_to && f.date_from > f.date_to) return 'Start date must be on or before end date.'
  for (const [low, high, max, integer] of [
    ['min_frp', 'max_frp', Infinity, false],
    ['min_risk_score', 'max_risk_score', 100, false],
    ['min_persistence', 'max_persistence', 30, true],
  ] as const) {
    for (const key of [low, high]) {
      if (f[key] !== '' && (!Number.isFinite(Number(f[key])) || Number(f[key]) < (integer ? 1 : 0) ||
        Number(f[key]) > max || (integer && !Number.isInteger(Number(f[key]))))) return 'Check numeric ranges: FRP ≥ 0, score 0–100, persistence 1–30 whole days.'
    }
    if (f[low] !== '' && f[high] !== '' && Number(f[low]) > Number(f[high])) return 'Range minimum must not exceed maximum.'
  }
  const b = [f.west, f.south, f.east, f.north]
  if (b.some(Boolean)) {
    if (!b.every(v => v.trim() !== '' && Number.isFinite(Number(v)))) return 'Provide all four bounding-box coordinates.'
    const [w, s, e, n] = b.map(Number)
    if (!(w >= -180 && w < e && e <= 180 && s >= -90 && s < n && n <= 90)) return 'Use west < east and south < north within valid latitude/longitude bounds.'
  }
  return null
}
export function filterParams(filters: Filters): URLSearchParams {
  const error = validateFilters(filters)
  if (error) throw new Error(error)
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(filters)) {
    if (v !== '' && !['max_persistence', 'west', 'south', 'east', 'north'].includes(k)) p.set(k, v)
  }
  if (filters.west !== '') p.set('bbox', [filters.west, filters.south, filters.east, filters.north].join(','))
  return p
}
export function localPersistence(rows: Hotspot[], filters: Filters) {
  return filters.max_persistence === '' ? rows : rows.filter(h => h.persistence_count_30d <= Number(filters.max_persistence))
}
