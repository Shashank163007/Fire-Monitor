import { readFileSync } from 'node:fs'
import { hotspotSchema, groupSchema } from '../api/schema'
const read = (name: string): unknown => JSON.parse(readFileSync(new URL('../../../backend/data/' + name, import.meta.url), 'utf8'))
export const realRows = hotspotSchema.array().parse(read('demo_hotspots.json'))
export const realGroups = groupSchema.array().parse(read('demo_alert_groups.json'))
export const realManifest = read('demo_manifest.json') as {
  total_hotspots: number; class_counts: { industrial: number; wildfire: number; unknown: number };
  risk_band_counts: { critical: number; high: number; moderate: number; low: number };
  risk_distribution: unknown[]; limitations: string[]; disclaimer: string;
}
export const row = realRows[0]
