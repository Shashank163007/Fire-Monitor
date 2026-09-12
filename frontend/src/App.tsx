import { lazy, Suspense, useCallback, useState } from 'react'
import { motion, MotionConfig } from 'framer-motion'
import { ArrowUpRight, BookOpen, ChevronRight, Radio, ShieldCheck } from 'lucide-react'
import { api } from './api/client'
import { useDashboard, useHotspot } from './state/useDashboard'
import { EMPTY_FILTERS, INITIAL_QUERY } from './state/filters'
import type { Filters, SortField } from './state/filters'
import { Connection, ErrorState, LoadingState } from './components/Status'
import { Summary } from './components/Summary'
import { FilterPanel } from './components/FilterPanel'
import { DetailPanel } from './components/DetailPanel'
import { ObservationList } from './components/ObservationList'
import { Methodology } from './components/Methodology'
import { AlertDrawer } from './components/AlertDrawer'
const Globe = lazy(() => import('./components/Globe'))

export default function App() {
  const [query, setQuery] = useState(INITIAL_QUERY)
  const [revision, setRevision] = useState(0)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [modal, setModal] = useState<'methodology' | 'alerts' | null>(null)
  const state = useDashboard(query, revision)
  const data = state.phase === 'ready' ? state.data : undefined
  const detail = useHotspot(data ? selectedId : null)
  const clearSelection = useCallback(() => setSelectedId(null), [])
  const apply = (filters: Filters) => { clearSelection(); setQuery(q => ({ ...q, filters })) }
  const resetFilters = () => apply({ ...EMPTY_FILTERS })
  const sort = (sort: SortField, order: 'asc' | 'desc') => setQuery(q => ({ ...q, sort, order }))
  const selectAlert = (id: string) => {
    // A global queue item must be visible even if it was excluded by active filters.
    if (!data?.hotspots.some(h => h.hotspot_id === id)) setQuery(q => ({ ...q, filters: { ...EMPTY_FILTERS } }))
    setSelectedId(id)
  }
  const selected = data?.hotspots.find(h => h.hotspot_id === selectedId) ?? null
  return <MotionConfig reducedMotion="user"><div className="app-shell">
    <a href="#observation-index" className="skip-link">Skip to observation index</a>
    <header className="topbar"><a href="/" className="brand" aria-label="SatBurn home"><img src="/satburn.svg" alt="SatBurn orbital logo"/><span>SATBURN<small>THERMAL OBSERVATION DESK</small></span></a>
      <div className="scope-header"><span className="eyebrow">WESTERN INDIA <ChevronRight size={11}/> RETROSPECTIVE REVIEW</span><span>{data ? `${data.meta.geographic_bounds.min_latitude}–${data.meta.geographic_bounds.max_latitude}°N · ${data.meta.geographic_bounds.min_longitude}–${data.meta.geographic_bounds.max_longitude}°E` : 'Region awaiting API'}<i/> {data ? `${data.meta.period.date_from} — ${data.meta.period.date_to}` : 'Dates awaiting API'}</span></div>
      <div className="nav-actions"><div className="status-stack"><span className="demo-badge"><span/>DEMO SNAPSHOT / LOCAL API</span><Connection state={state.phase}/></div><button className="method-button" onClick={() => setModal('methodology')}><BookOpen size={16}/><span>Methodology</span></button></div>
    </header>
    <main><section className="page-heading"><div><div className="eyebrow"><span className="accent-line"/>SATELLITE EVIDENCE. HUMAN JUDGEMENT.</div><h1>A wider view.<em>A closer understanding.</em></h1></div><div className="heading-note"><ShieldCheck size={19}/><p>Evidence-linked review context.<br/><span>Proxy categories. No verified fire causes.</span></p></div></section>
      {state.phase === 'loading' && <LoadingState/>}
      {state.phase === 'error' && <ErrorState message={state.error.message} offline={state.error.kind === 'offline'} retry={() => setRevision(r => r+1)}/>}
      {data && <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: .2 }}>
        <Summary stats={data.stats} distribution={data.distribution} onAlerts={() => setModal('alerts')}/>
        <div className="workspace">
          <FilterPanel key={JSON.stringify(query.filters)} filters={query.filters} onApply={apply}/>
          <Suspense fallback={<div className="globe-panel"><LoadingState/></div>}><Globe rows={data.hotspots} meta={data.meta} selected={selected} select={setSelectedId} resetSelection={clearSelection}/></Suspense>
          <DetailPanel id={selectedId} row={detail?.row} error={detail?.error} close={clearSelection}/>
        </div>
        <div className="context-strip"><span><Radio size={13}/>Rule-based weak-label fallback · classifier not operational</span><button onClick={() => setModal('alerts')}>Review queue · {data.alerts.length} observations / {data.groups.length} groups<ArrowUpRight size={14}/></button></div>
        <div id="observation-index"><ObservationList key={JSON.stringify(query)} rows={data.hotspots} query={query} onSort={sort} selectedId={selectedId} select={id => { setSelectedId(id); document.querySelector('.workspace')?.scrollIntoView({ block: 'start', behavior: 'instant' }) }} reset={resetFilters}/></div>
      </motion.div>}
    </main>
    <footer><span><img src="/satburn.svg" alt="" aria-hidden="true"/>SatBurn <i/>Retrospective observation, considered carefully.</span><span>Natural Earth reference outlines · local assets only <i/><button onClick={() => setModal('methodology')}>Sources & limitations</button></span></footer>
    <div className="connection-address">Configured local API: {api.base}</div>
    {modal === 'methodology' && <Methodology meta={data?.meta} close={() => setModal(null)}/>}
    {modal === 'alerts' && data && <AlertDrawer alerts={data.alerts} groups={data.groups} select={selectAlert} close={() => setModal(null)}/>}
  </div></MotionConfig>
}
