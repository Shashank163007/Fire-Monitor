import { useState } from 'react'
import { ArrowUpRight, Layers3 } from 'lucide-react'
import type { Alert, AlertGroup } from '../api/schema'
import { numberText, observationTime } from '../lib/presentation'
import { CategoryBadge, RiskBadge } from './Badges'
import { Modal } from './Modal'
export function AlertDrawer({ alerts, groups, select, close }: { alerts: Alert[]; groups: AlertGroup[]; select: (id: string) => void; close: () => void }) {
  const [tab, setTab] = useState<'alerts' | 'groups'>('alerts')
  const [sort, setSort] = useState<'score' | 'date'>('score')
  const [order, setOrder] = useState<'asc' | 'desc'>('desc')
  const compare = (a: number | string, b: number | string) => (a < b ? -1 : a > b ? 1 : 0) * (order === 'asc' ? 1 : -1)
  const sortedAlerts = [...alerts].sort((a, b) => compare(sort === 'score' ? a.risk_score : a.acq_date + a.acq_time, sort === 'score' ? b.risk_score : b.acq_date + b.acq_time) || a.hotspot_id.localeCompare(b.hotspot_id))
  const sortedGroups = [...groups].sort((a, b) => compare(sort === 'score' ? a.maximum_risk_score : a.acq_date, sort === 'score' ? b.maximum_risk_score : b.acq_date) || a.alert_group_id.localeCompare(b.alert_group_id))
  const focus = (id: string) => { select(id); close() }
  return <Modal title="The human-review queue" close={close} className="alert-drawer">
    <p className="modal-lede">Full snapshot · high and critical review priority. This local queue does not transmit alerts or recommend dispatch.</p>
    <div className="drawer-controls"><div className="segmented"><button aria-pressed={tab === 'alerts'} onClick={() => setTab('alerts')}>Observations <b>{alerts.length}</b></button><button aria-pressed={tab === 'groups'} onClick={() => setTab('groups')}>Daily groups <b>{groups.length}</b></button></div>
      <label className="field"><span>Queue sort</span><select value={sort} onChange={e => setSort(e.target.value as 'score' | 'date')}><option value="score">Review score</option><option value="date">Acquisition date</option></select></label>
      <button aria-label="Toggle queue sort direction" onClick={() => setOrder(order === 'desc' ? 'asc' : 'desc')}>{order === 'desc' ? 'Descending ↓' : 'Ascending ↑'}</button>
    </div>
    <div className="queue-items">{tab === 'alerts' ? sortedAlerts.map(a => <button className="queue-item" key={a.alert_id} onClick={() => focus(a.hotspot_id)} aria-label={'Review alert ' + a.hotspot_id}>
      <div className="queue-score">{numberText(a.risk_score, 2)}<small>review score</small></div><div><CategoryBadge category={a.predicted_class}/><p>{observationTime(a)}</p><small>{a.hotspot_id.slice(0, 16)} · {numberText(a.frp)} MW ? {a.persistence_count_30d} persistence days</small></div><ArrowUpRight size={18}/>
    </button>) : sortedGroups.map(g => <button className="queue-item group-item" key={g.alert_group_id} onClick={() => focus(g.representative_hotspot_id)}>
      <Layers3 size={22}/><div><strong>{g.acq_date} · {g.hotspot_count} observations</strong><p>{g.group_explanation}</p><small>Grid {g.grid_min_latitude}–{g.grid_max_latitude}°N / {g.grid_min_longitude}–{g.grid_max_longitude}°E · Max score {numberText(g.maximum_risk_score, 2)}</small><RiskBadge band={g.highest_risk_band}/><small>Open representative observation ↗</small></div>
    </button>)}
    {!(tab === 'alerts' ? alerts.length : groups.length) && <p role="status">No review items are available.</p>}</div>
  </Modal>
}
