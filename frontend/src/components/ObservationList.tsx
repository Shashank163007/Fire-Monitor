import { useState } from 'react'
import { ArrowDownWideNarrow, ChevronLeft, ChevronRight, MoveUpRight } from 'lucide-react'
import type { Hotspot } from '../api/schema'
import type { QueryState, SortField } from '../state/filters'
import { numberText, observationTime } from '../lib/presentation'
import { CategoryBadge, RiskBadge } from './Badges'
import { EmptyState } from './Status'
export function ObservationList({ rows, query, onSort, selectedId, select, reset }: {
  rows: Hotspot[]; query: QueryState; onSort: (sort: SortField, order: 'asc' | 'desc') => void;
  selectedId: string | null; select: (id: string) => void; reset: () => void;
}) {
  const [page, setPage] = useState(0)
  const size = 8
  const current = Math.min(page, Math.max(0, Math.ceil(rows.length / size) - 1))
  return <section className="panel observation-list" aria-label="Keyboard-accessible observations">
    <div className="list-heading"><div><span className="eyebrow">OBSERVATION INDEX</span><h2>Explore the evidence <span>{rows.length} matching</span></h2></div>
      <div className="sort-controls"><ArrowDownWideNarrow size={15}/><label className="sr-only" htmlFor="observation-sort">Sort observations</label>
        <select id="observation-sort" value={query.sort} onChange={e => { setPage(0); onSort(e.target.value as SortField, query.order) }}><option value="acq_date">Acquisition date</option><option value="risk_score">Review score</option><option value="frp">FRP</option><option value="persistence_count_30d">Persistence</option></select>
        <button onClick={() => { setPage(0); onSort(query.sort, query.order === 'asc' ? 'desc' : 'asc') }} aria-label="Toggle observation sort direction">{query.order === 'asc' ? 'Ascending ↑' : 'Descending ↓'}</button>
      </div>
    </div>
    {!rows.length ? <EmptyState reset={reset}/> : <><div className="table-scroll"><table><thead><tr><th>Observation / UTC</th><th>Weak-label context</th><th>Review priority</th><th>FRP · MW</th><th>Persistence</th><th><span className="sr-only">Inspect</span></th></tr></thead><tbody>{rows.slice(current * size, (current + 1) * size).map(row =>
      <tr key={row.hotspot_id} className={selectedId === row.hotspot_id ? 'selected-row' : ''}><td><button className="observation-link" onClick={() => select(row.hotspot_id)} aria-label={'Inspect observation ' + row.hotspot_id}><span>{row.hotspot_id.slice(0, 12)}</span><small>{observationTime(row)}</small></button></td><td><CategoryBadge category={row.predicted_class}/></td><td><b>{numberText(row.risk_score, 2)}</b> <RiskBadge band={row.risk_band}/></td><td>{numberText(row.frp)}</td><td>{row.persistence_count_30d} days</td><td><MoveUpRight size={14} aria-hidden="true"/></td></tr>)}</tbody></table></div>
      <div className="pagination"><span>Showing {current * size + 1}–{Math.min((current + 1) * size, rows.length)} of {rows.length}</span><div><button className="icon-button" aria-label="Previous observations" disabled={current === 0} onClick={() => setPage(current - 1)}><ChevronLeft size={16}/></button><span>Page {current + 1} / {Math.ceil(rows.length / size)}</span><button className="icon-button" aria-label="Next observations" disabled={(current + 1) * size >= rows.length} onClick={() => setPage(current + 1)}><ChevronRight size={16}/></button></div></div></>}
  </section>
}
