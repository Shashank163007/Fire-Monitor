import { useState } from 'react'
import { RotateCcw, SlidersHorizontal } from 'lucide-react'
import { activeFilterCount, EMPTY_FILTERS, validateFilters } from '../state/filters'
import type { Filters } from '../state/filters'

export function FilterPanel({ filters, onApply }: { filters: Filters; onApply: (f: Filters) => void }) {
  const [draft, setDraft] = useState(filters)
  const [error, setError] = useState<string | null>(null)
  const field = (key: keyof Filters, value: string) => { setDraft(d => ({ ...d, [key]: value })); setError(null) }
  const numberInput = (key: keyof Filters, label: string, min: number, max?: number, step = 'any') =>
    <label className="field"><span>{label}</span><input type="number" min={min} max={max} step={step} placeholder="Any"
      value={draft[key]} onChange={e => field(key, e.target.value)}/></label>
  const reset = () => { setDraft(EMPTY_FILTERS); setError(null); onApply({ ...EMPTY_FILTERS }) }
  return <aside className="panel filter-panel" aria-label="Observation filters">
    <div className="panel-heading"><h2><SlidersHorizontal size={15}/>Filter observations</h2><span className="count-pill" aria-label="Active filter count">{activeFilterCount(filters)}</span></div>
    <form onSubmit={e => { e.preventDefault(); const message = validateFilters(draft); setError(message); if (!message) onApply({ ...draft }) }}>
      <label className="field"><span>Context category</span><select value={draft.predicted_class} onChange={e => field('predicted_class', e.target.value)}>
        <option value="">All categories</option><option value="industrial">Industrial candidate</option><option value="wildfire">Wildfire candidate</option><option value="unknown">Unknown</option>
      </select></label>
      <label className="field"><span>Review-priority band</span><select value={draft.risk_band} onChange={e => field('risk_band', e.target.value)}>
        <option value="">All bands</option><option value="critical">Critical</option><option value="high">High</option><option value="moderate">Moderate</option><option value="low">Low</option>
      </select></label>
      <fieldset><legend>Acquisition window · UTC</legend><div className="field-pair">
        <label className="field"><span>From date</span><input type="date" value={draft.date_from} onChange={e => field('date_from', e.target.value)}/></label>
        <label className="field"><span>To date</span><input type="date" value={draft.date_to} onChange={e => field('date_to', e.target.value)}/></label>
      </div></fieldset>
      <label className="field"><span>Day / night observation</span><select value={draft.day_night} onChange={e => field('day_night', e.target.value)}>
        <option value="">Day and night</option><option value="D">Day only</option><option value="N">Night only</option>
      </select></label>
      <fieldset><legend>Fire radiative power · MW</legend><div className="field-pair">{numberInput('min_frp', 'Minimum FRP', 0)}{numberInput('max_frp', 'Maximum FRP', 0)}</div></fieldset>
      <fieldset><legend>Review score · 0–100</legend><div className="field-pair">{numberInput('min_risk_score', 'Minimum score', 0, 100)}{numberInput('max_risk_score', 'Maximum score', 0, 100)}</div></fieldset>
      <fieldset><legend>Persistence · distinct days / 30d</legend><div className="field-pair">{numberInput('min_persistence', 'Minimum persistence', 1, 30, '1')}{numberInput('max_persistence', 'Maximum persistence', 1, 30, '1')}</div></fieldset>
      <details><summary>Geographic bounds</summary><div className="field-pair">{numberInput('west', 'West longitude', -180, 180)}{numberInput('east', 'East longitude', -180, 180)}{numberInput('south', 'South latitude', -90, 90)}{numberInput('north', 'North latitude', -90, 90)}</div></details>
      {error && <p role="alert" className="inline-error">{error}</p>}
      <button className="primary-button full" type="submit">Apply filters <span>↗</span></button>
      <button className="quiet-button full" type="button" onClick={reset}><RotateCcw size={13}/>Reset filters</button>
    </form>
  </aside>
}
