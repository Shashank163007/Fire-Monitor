import type { Category, Hotspot, RiskBand } from '../api/schema'
export const CATEGORY: Record<Category, { label: string; color: string; code: string }> = {
  industrial: { label: 'Industrial candidate', color: '#f5a45d', code: 'industrial_candidate' },
  wildfire: { label: 'Wildfire candidate', color: '#f06b70', code: 'wildfire_candidate' },
  unknown: { label: 'Unknown', color: '#9ba8b9', code: 'unknown' },
}
export const BAND: Record<RiskBand, { label: string; color: string; ring: number }> = {
  critical: { label: 'Critical priority', color: '#ec7f93', ring: 2.4 },
  high: { label: 'High priority', color: '#f5a45d', ring: 2 },
  moderate: { label: 'Moderate priority', color: '#ddc17d', ring: 1.5 },
  low: { label: 'Low priority', color: '#8fa7b7', ring: 1.1 },
}
export const CONFIDENCE = { l: 'Low', n: 'Nominal', h: 'High' }
export function observationTime(h: Pick<Hotspot, 'acq_date' | 'acq_time'>) {
  return `${h.acq_date} · ${h.acq_time.slice(0, 2)}:${h.acq_time.slice(2)} UTC`
}
export function numberText(value: number | null | undefined, digits = 1): string {
  return value == null || !Number.isFinite(value) ? 'Not available' : value.toLocaleString('en-US', { maximumFractionDigits: digits })
}
export function coordinates(latitude: number, longitude: number, radius = 2): [number, number, number] {
  const lat = latitude * Math.PI / 180, lon = longitude * Math.PI / 180
  return [radius * Math.cos(lat) * Math.cos(lon), radius * Math.sin(lat), -radius * Math.cos(lat) * Math.sin(lon)]
}
