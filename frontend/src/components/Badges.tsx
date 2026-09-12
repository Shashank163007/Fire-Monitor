import type { Category, RiskBand } from '../api/schema'
import { BAND, CATEGORY } from '../lib/presentation'
export function CategoryBadge({ category }: { category: Category }) {
  return <span className="category-badge" style={{ color: CATEGORY[category].color }}><i style={{ background: CATEGORY[category].color }}/>{CATEGORY[category].label}</span>
}
export function RiskBadge({ band }: { band: RiskBand }) {
  return <span className={'risk-badge risk-' + band} style={{ color: BAND[band].color }}>{BAND[band].label}</span>
}
