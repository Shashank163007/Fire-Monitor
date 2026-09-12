import { z } from 'zod'

export const categorySchema = z.enum(['industrial', 'wildfire', 'unknown'])
export const bandSchema = z.enum(['critical', 'high', 'moderate', 'low'])
const count = z.number().int().nonnegative()
const number = z.number().finite()
const score = number.min(0).max(100)
const date = z.string().regex(/^\d{4}-\d{2}-\d{2}$/)
export const hotspotSchema = z.object({
  hotspot_id: z.string().regex(/^[0-9a-f]{64}$/),
  latitude: number.min(-90).max(90), longitude: number.min(-180).max(180),
  acq_date: date, acq_time: z.string().regex(/^(?:[01]\d|2[0-3])[0-5]\d$/),
  frp: number.nonnegative(), brightness: number.positive(),
  confidence: z.enum(['l', 'n', 'h']), day_night: z.enum(['D', 'N']),
  distance_to_industrial_km: number.nonnegative().nullable(),
  persistence_count_30d: z.number().int().min(1).max(30), land_cover_class: z.string(),
  predicted_class: categorySchema, classification_source: z.literal('rule_based_weak_label_fallback'),
  class_probability: z.null(), risk_score: score, risk_band: bandSchema,
  frp_points: number.min(0).max(40), persistence_points: number.min(0).max(30),
  confidence_points: number.min(0).max(20), night_points: number.min(0).max(10),
  primary_risk_driver: z.enum(['thermal_intensity', 'persistence', 'observation_confidence', 'night_observation']),
  explanation: z.string(),
})
export const alertSchema = hotspotSchema.extend({ alert_id: z.string() })
export const groupSchema = z.object({
  alert_group_id: z.string(), acq_date: date,
  grid_min_latitude: number, grid_max_latitude: number,
  grid_min_longitude: number, grid_max_longitude: number,
  hotspot_count: count, maximum_risk_score: score, highest_risk_band: z.enum(['high', 'critical']),
  industrial_count: count, wildfire_count: count, unknown_count: count, mean_frp: number,
  maximum_persistence_count_30d: count, representative_hotspot_id: z.string(),
  group_explanation: z.string(),
})
const classCounts = z.object({ industrial: count, wildfire: count, unknown: count })
const bandCounts = z.object({ critical: count, high: count, moderate: count, low: count })
const numericSummary = z.object({ minimum: number, median: number, mean: number, maximum: number })
export const healthSchema = z.object({
  status: z.literal('ok'), service: z.string(), schema_version: z.string(),
  dataset_loaded: z.literal(true), total_hotspots: count,
})
export const metaSchema = z.object({
  project_title: z.string(), dataset_mode: z.literal('retrospective_demo'),
  geographic_bounds: z.object({
    min_latitude: number, max_latitude: number, min_longitude: number, max_longitude: number,
    boundary_policy: z.literal('south_west_inclusive_north_east_exclusive'),
  }),
  period: z.object({ date_from: date, date_to: date }),
  classification_source: z.literal('rule_based_weak_label_fallback'), classifier_operational: z.literal(false),
  scoring_method: z.string(), total_hotspots: count, class_counts: classCounts, risk_band_counts: bandCounts,
  source_stage: count, data_disclaimer: z.string(), limitations: z.array(z.string()),
})
export const statsSchema = z.object({
  total_hotspots: count, class_counts: classCounts, risk_band_counts: bandCounts,
  day_night_counts: z.record(z.string(), count), confidence_counts: z.record(z.string(), count),
  high_priority_alert_count: count, alert_group_count: count,
  risk_score: numericSummary, frp: numericSummary, persistence: numericSummary,
})
export const distributionSchema = z.object({
  total_hotspots: count,
  items: z.array(z.object({
    predicted_class: z.enum(['industrial', 'wildfire', 'unknown', 'overall']),
    risk_band: z.enum(['critical', 'high', 'moderate', 'low', 'all']), hotspot_count: count,
    minimum_score: score.nullable(), median_score: score.nullable(),
    mean_score: score.nullable(), maximum_score: score.nullable(),
  })),
})
export const geoSchema = z.object({
  type: z.literal('FeatureCollection'),
  features: z.array(z.object({
    type: z.literal('Feature'),
    geometry: z.object({ type: z.literal('Point'), coordinates: z.tuple([number, number]) }),
    properties: hotspotSchema.pick({
      hotspot_id: true, acq_date: true, acq_time: true, predicted_class: true,
      classification_source: true, frp: true, persistence_count_30d: true, risk_score: true,
      risk_band: true, day_night: true, confidence: true, primary_risk_driver: true, explanation: true,
    }),
  })),
})
export function pageSchema<T extends z.ZodType>(item: T) {
  return z.object({
    items: z.array(item), total: count, limit: count.positive(), offset: count, returned: count,
    applied_filters: z.record(z.string(), z.union([z.string(), number])),
    sort_by: z.string(), sort_order: z.enum(['asc', 'desc']),
  })
}
export type Category = z.infer<typeof categorySchema>
export type RiskBand = z.infer<typeof bandSchema>
export type Hotspot = z.infer<typeof hotspotSchema>
export type Alert = z.infer<typeof alertSchema>
export type AlertGroup = z.infer<typeof groupSchema>
export type Health = z.infer<typeof healthSchema>
export type Metadata = z.infer<typeof metaSchema>
export type Statistics = z.infer<typeof statsSchema>
export type RiskDistribution = z.infer<typeof distributionSchema>
export type GeoJSON = z.infer<typeof geoSchema>
export type Page<T> = { items: T[]; total: number; limit: number; offset: number; returned: number;
  applied_filters: Record<string, string | number>; sort_by: string; sort_order: 'asc' | 'desc' }
