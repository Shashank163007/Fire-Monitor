import { z } from 'zod'
import { alertSchema, distributionSchema, geoSchema, groupSchema, healthSchema, hotspotSchema,
  metaSchema, pageSchema, statsSchema } from './schema'
import type { Alert, AlertGroup, GeoJSON, Health, Hotspot, Metadata, RiskDistribution, Statistics } from './schema'
import { filterParams, localPersistence } from '../state/filters'
import type { QueryState } from '../state/filters'

export class ApiError extends Error {
  constructor(message: string, public kind: 'offline' | 'http' | 'contract') { super(message); this.name = 'ApiError' }
}
export function localBase(value: string): string {
  const url = new URL(value)
  if (!['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname) ||
      !['http:', 'https:'].includes(url.protocol) || url.username || url.password ||
      url.pathname !== '/' || url.search || url.hash) throw new Error('VITE_API_BASE_URL must be a loopback HTTP(S) origin.')
  return url.origin
}
export interface Snapshot {
  health: Health; meta: Metadata; stats: Statistics; distribution: RiskDistribution;
  hotspots: Hotspot[]; geo: GeoJSON; alerts: Alert[]; groups: AlertGroup[]; serverMatched: number;
}
export class ApiClient {
  readonly base: string
  constructor(base: string) { this.base = localBase(base) }
  async get<T>(path: string, schema: z.ZodType<T>, signal?: AbortSignal, params = new URLSearchParams()): Promise<T> {
    if (!/^\/api\/v1\/(health|meta|stats|hotspots(?:\.geojson|\/[0-9a-f]{64})?|alerts|alert-groups|risk-distribution)$/.test(path))
      throw new ApiError('Unrecognised API path.', 'contract')
    const url = new URL(path, this.base)
    url.search = params.toString()
    try {
      const response = await fetch(url, { method: 'GET', signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(15000)]) : AbortSignal.timeout(15000),
        cache: 'no-store', credentials: 'omit', redirect: 'error' })
      if (!response.ok) throw new ApiError(`Local API returned HTTP ${response.status}. Check the filters or retry.`, 'http')
      let raw: unknown
      try { raw = await response.json() } catch { throw new ApiError('The API returned invalid JSON.', 'contract') }
      const parsed = schema.safeParse(raw)
      if (!parsed.success) throw new ApiError('The API response does not match the Stage 6 contract. No substitute data was loaded.', 'contract')
      return parsed.data
    } catch (error) {
      if (signal?.aborted) throw error
      if (error instanceof ApiError) throw error
      throw new ApiError('Local API unavailable. Start the backend on the configured address, then reconnect.', 'offline')
    }
  }
  async allPages<T extends z.ZodType>(path: string, item: T, signal: AbortSignal, params = new URLSearchParams()): Promise<z.infer<T>[]> {
    const rows: z.infer<T>[] = []
    let total: number | undefined
    while (total === undefined || rows.length < total) {
      const query = new URLSearchParams(params)
      query.set('limit', '500'); query.set('offset', String(rows.length))
      const page = await this.get(path, pageSchema(item), signal, query)
      if (page.offset !== rows.length || page.returned !== page.items.length ||
          page.items.length > 500 || (total !== undefined && total !== page.total) ||
          page.items.length + rows.length > page.total || (!page.items.length && page.total > rows.length))
        throw new ApiError('Inconsistent pagination from the local API.', 'contract')
      total = page.total
      rows.push(...page.items)
    }
    return rows
  }
  health(signal: AbortSignal) { return this.get('/api/v1/health', healthSchema, signal) }
  detail(id: string, signal: AbortSignal) { return this.get('/api/v1/hotspots/' + id, hotspotSchema, signal) }
  async snapshot(query: QueryState, signal: AbortSignal): Promise<Snapshot> {
    const params = filterParams(query.filters)
    const sorted = new URLSearchParams(params)
    sorted.set('sort_by', query.sort); sorted.set('sort_order', query.order)
    const [health, meta, stats, distribution, rows, geo, alerts, groups] = await Promise.all([
      this.health(signal), this.get('/api/v1/meta', metaSchema, signal),
      this.get('/api/v1/stats', statsSchema, signal), this.get('/api/v1/risk-distribution', distributionSchema, signal),
      this.allPages('/api/v1/hotspots', hotspotSchema, signal, sorted),
      this.get('/api/v1/hotspots.geojson', geoSchema, signal, params),
      this.allPages('/api/v1/alerts', alertSchema, signal),
      this.allPages('/api/v1/alert-groups', groupSchema, signal),
    ])
    const coords = new Map(geo.features.map(f => [f.properties.hotspot_id, f.geometry.coordinates]))
    if (new Set(rows.map(h => h.hotspot_id)).size !== rows.length || coords.size !== geo.features.length ||
        coords.size !== rows.length || rows.some(h => {
          const p = coords.get(h.hotspot_id); return !p || p[0] !== h.longitude || p[1] !== h.latitude
        }) || health.total_hotspots !== meta.total_hotspots || meta.total_hotspots !== stats.total_hotspots ||
        distribution.total_hotspots !== stats.total_hotspots || alerts.length !== stats.high_priority_alert_count ||
        groups.length !== stats.alert_group_count)
      throw new ApiError('Snapshot responses disagree. Reconnect to a consistent local dataset.', 'contract')
    return { health, meta, stats, distribution, hotspots: localPersistence(rows, query.filters),
      geo, alerts, groups, serverMatched: rows.length }
  }
}
export const api = new ApiClient(import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000')
