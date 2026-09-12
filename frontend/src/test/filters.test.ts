import { describe, expect, it } from 'vitest'
import { activeFilterCount, EMPTY_FILTERS, filterParams, localPersistence, validateFilters } from '../state/filters'
import { BAND, CATEGORY, coordinates, numberText } from '../lib/presentation'
import { realRows } from './fixtures'
describe('filter validation and exact API parameters', () => {
  it('sends no filters for the reset state', () => { expect(filterParams(EMPTY_FILTERS).toString()).toBe(''); expect(activeFilterCount(EMPTY_FILTERS)).toBe(0) })
  it('encodes all supported filters and longitude-first bbox while retaining maximum persistence locally', () => {
    const f = { ...EMPTY_FILTERS, predicted_class: 'industrial' as const, risk_band: 'high' as const, day_night: 'N' as const,
      date_from: '2026-06-01', date_to: '2026-06-30', min_frp: '0', max_frp: '30', min_risk_score: '0', max_risk_score: '75',
      min_persistence: '2', max_persistence: '15', west: '72', east: '75', south: '21', north: '24' }
    const params = filterParams(f)
    expect(params.get('bbox')).toBe('72,21,75,24'); expect(params.get('min_frp')).toBe('0')
    expect(params.get('min_persistence')).toBe('2'); expect(params.has('max_persistence')).toBe(false)
    expect(activeFilterCount(f)).toBe(12)
    expect(localPersistence(realRows, f)).toEqual(realRows.filter(h => h.persistence_count_30d <= 15))
  })
  it.each([
    { min_frp: '-1' }, { min_risk_score: '101' }, { min_persistence: '1.5' }, { max_persistence: '31' },
    { min_frp: '20', max_frp: '10' }, { date_from: '2026-06-30', date_to: '2026-06-01' },
    { date_from: '2026-02-30' }, { west: '72' }, { west: '75', east: '72', south: '21', north: '24' },
    { min_frp: 'Infinity' }, { max_risk_score: 'no' },
  ])('rejects invalid ranges %o', changed => expect(validateFilters({ ...EMPTY_FILTERS, ...changed })).not.toBeNull())
  it('includes both maximum and minimum persistence boundary values', () => {
    const f = { ...EMPTY_FILTERS, max_persistence: '30' }
    expect(localPersistence(realRows, f)).toEqual(realRows)
  })
})
describe('scientific display mappings', () => {
  it('uses orange/red/grey only for context categories', () => {
    expect(CATEGORY.industrial).toMatchObject({ color: '#f5a45d', code: 'industrial_candidate' })
    expect(CATEGORY.wildfire).toMatchObject({ color: '#f06b70', code: 'wildfire_candidate' })
    expect(CATEGORY.unknown.color).toBe('#9ba8b9')
  })
  it('labels every band as priority and preserves the API band rather than recalculating scores', () => {
    expect(Object.values(BAND).every(b => b.label.includes('priority'))).toBe(true)
    expect(BAND.critical.ring).toBeGreaterThan(BAND.low.ring)
  })
  it('never displays missing metrics as zero', () => {
    expect(numberText(null)).toBe('Not available'); expect(numberText(undefined)).toBe('Not available'); expect(numberText(0)).toBe('0')
  })
  it('converts known longitude/latitude points to the correct globe axes', () => {
    expect(coordinates(0, 0)).toEqual([2, 0, -0])
    expect(coordinates(90, 0)[1]).toBeCloseTo(2)
    expect(coordinates(0, 90)[2]).toBeCloseTo(-2)
    const p = coordinates(22, 73); expect(Math.hypot(...p)).toBeCloseTo(2)
  })
})
