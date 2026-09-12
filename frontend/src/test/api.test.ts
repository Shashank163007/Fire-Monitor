import { describe, expect, it, vi } from 'vitest'
import { ApiClient, localBase } from '../api/client'
import { geoSchema, hotspotSchema, pageSchema } from '../api/schema'
import { realRows, row } from './fixtures'
const client = new ApiClient('http://127.0.0.1:8000')
describe('runtime API parsing', () => {
  it('parses every real Stage 6 row and retains null probability', () => {
    expect(hotspotSchema.array().parse(realRows)).toEqual(realRows)
    expect(realRows.every(h => h.class_probability === null)).toBe(true)
  })
  it.each(['frp', 'risk_score', 'latitude', 'persistence_count_30d'])('rejects missing %s instead of fabricating a value', field => {
    const incomplete: Record<string, unknown> = { ...row }; delete incomplete[field]
    expect(hotspotSchema.safeParse(incomplete).success).toBe(false)
  })
  it('rejects non-null probabilities, unknown categories and nonfinite scores', () => {
    for (const changed of [{ class_probability: .8 }, { predicted_class: 'flare' }, { risk_score: NaN }, { risk_score: 101 }])
      expect(hotspotSchema.safeParse({ ...row, ...changed }).success).toBe(false)
  })
  it('parses the exact GeoJSON projection', () => {
    const { hotspot_id, acq_date, acq_time, predicted_class, classification_source, frp, persistence_count_30d,
      risk_score, risk_band, day_night, confidence, primary_risk_driver, explanation } = row
    const geo = { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [row.longitude, row.latitude] },
      properties: { hotspot_id, acq_date, acq_time, predicted_class, classification_source, frp, persistence_count_30d, risk_score, risk_band, day_night, confidence, primary_risk_driver, explanation } }] }
    expect(geoSchema.parse(geo).features[0].geometry.coordinates).toEqual([row.longitude, row.latitude])
  })
  it('requires pagination metadata', () => { expect(pageSchema(hotspotSchema).safeParse({ items: [] }).success).toBe(false) })
})
describe('local-only client and pagination', () => {
  it.each(['http://127.0.0.1:8000', 'http://localhost:8000', 'http://[::1]:8000'])('allows loopback origin %s', value => expect(localBase(value)).toBe(value))
  it.each(['https://example.com', 'https://127.0.0.1.evil.test', 'http://localhost:8000/path', 'http://user:pass@localhost:8000', 'file:///data', 'http://localhost:8000?redirect=1'])('rejects non-local or ambiguous origin %s', value => expect(() => localBase(value)).toThrow())
  it('only sends GETs to the configured API and never forwards credentials or follows redirects', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(row)))
    vi.stubGlobal('fetch', fetcher)
    await client.detail(row.hotspot_id, new AbortController().signal)
    const [url, options] = fetcher.mock.calls[0]
    expect(url.toString()).toBe('http://127.0.0.1:8000/api/v1/hotspots/' + row.hotspot_id)
    expect(options).toMatchObject({ method: 'GET', credentials: 'omit', redirect: 'error' })
    await expect(client.get('https://example.com', hotspotSchema)).rejects.toThrow('Unrecognised')
    expect(fetcher).toHaveBeenCalledTimes(1)
  })
  it('follows server pages and preserves filters and sorting on every page', async () => {
    const rows = realRows
    const fetcher = vi.fn((url: URL) => {
      const offset = Number(url.searchParams.get('offset'))
      const items = rows.slice(offset, offset + 500)
      return Promise.resolve(new Response(JSON.stringify({ items, total: rows.length, limit: 500, offset, returned: items.length,
        applied_filters: { day_night: 'N' }, sort_by: 'risk_score', sort_order: 'desc' })))
    })
    vi.stubGlobal('fetch', fetcher)
    const loaded = await client.allPages('/api/v1/hotspots', hotspotSchema, new AbortController().signal, new URLSearchParams('day_night=N&sort_by=risk_score&sort_order=desc'))
    expect(loaded).toEqual(rows)
    expect(fetcher).toHaveBeenCalledTimes(Math.ceil(rows.length / 500))
    for (const [url] of fetcher.mock.calls) { expect(url.searchParams.get('day_night')).toBe('N'); expect(url.searchParams.get('sort_by')).toBe('risk_score') }
  })
  it('rejects stalled pagination rather than looping forever', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], total: 2, limit: 500, offset: 0, returned: 0, applied_filters: {}, sort_by: 'acq_date', sort_order: 'asc' }))))
    await expect(client.allPages('/api/v1/hotspots', hotspotSchema, new AbortController().signal)).rejects.toThrow('pagination')
  })
  it('distinguishes offline, HTTP, and contract errors', async () => {
    await expect(client.detail(row.hotspot_id, new AbortController().signal)).rejects.toMatchObject({ kind: 'offline' })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 422 })))
    await expect(client.detail(row.hotspot_id, new AbortController().signal)).rejects.toMatchObject({ kind: 'http' })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}')))
    await expect(client.detail(row.hotspot_id, new AbortController().signal)).rejects.toMatchObject({ kind: 'contract' })
  })
})
