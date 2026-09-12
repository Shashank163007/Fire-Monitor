import { Activity, ArrowUpRight, Factory, ScanEye, Trees } from 'lucide-react'
import type { RiskDistribution, Statistics } from '../api/schema'
import { BAND, numberText } from '../lib/presentation'
export function Summary({ stats, distribution, onAlerts }: { stats: Statistics; distribution: RiskDistribution; onAlerts: () => void }) {
  const cards = [
    { label: 'Total observations', value: stats.total_hotspots, sub: 'Snapshot detections', icon: ScanEye, color: '#cdd8e5' },
    { label: 'Industrial candidates', value: stats.class_counts.industrial, sub: 'Weak-label context', icon: Factory, color: '#f5a45d' },
    { label: 'Wildfire candidates', value: stats.class_counts.wildfire, sub: 'Weak-label context', icon: Trees, color: '#f06b70' },
    { label: 'Unknown context', value: stats.class_counts.unknown, sub: 'No usable category', icon: Activity, color: '#9ba8b9' },
  ]
  const bands = distribution.items.filter(r => r.predicted_class === 'overall' && r.risk_band !== 'all')
  return <section className="summary-section" aria-label="Full snapshot summary">
    <div className="summary-grid">{cards.map(c => <article className="summary-card" key={c.label}>
      <div className="card-caption">{c.label}<c.icon size={16} style={{ color: c.color }}/></div>
      <strong style={{ color: c.color }}>{numberText(c.value, 0)}</strong><span>{c.sub}</span>
    </article>)}
      <button className="summary-card alert-card" onClick={onAlerts}><div className="card-caption">High-priority review<ArrowUpRight size={16}/></div><strong>{numberText(stats.high_priority_alert_count, 0)}</strong><span>Open the local review queue</span></button>
    </div>
    <div className="distribution"><span className="eyebrow">REVIEW PRIORITY</span><div className="distribution-bar" aria-hidden="true">{bands.map(b => b.risk_band !== 'all' && <span key={b.risk_band} style={{ width: distribution.total_hotspots ? (b.hotspot_count / distribution.total_hotspots * 100) + '%' : '0%', background: BAND[b.risk_band].color }}/>)}</div>
      <div className="distribution-labels">{bands.map(b => b.risk_band !== 'all' && <span key={b.risk_band}><i style={{ background: BAND[b.risk_band].color }}/>{b.risk_band} <b>{b.hotspot_count}</b></span>)}</div>
      <span className="summary-scope">Full snapshot · unaffected by filters</span>
    </div>
  </section>
}
