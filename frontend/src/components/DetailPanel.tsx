import { Crosshair, Fingerprint, Info, X } from 'lucide-react'
import type { Hotspot } from '../api/schema'
import { CONFIDENCE, numberText, observationTime } from '../lib/presentation'
import { CategoryBadge, RiskBadge } from './Badges'
export function DetailPanel({ id, row, error, close }: { id: string | null; row?: Hotspot; error?: string; close: () => void }) {
  return <aside className="panel detail-panel" aria-label="Observation details" aria-live="polite">
    <div className="panel-heading"><h2><Crosshair size={15}/>Observation detail</h2>{id && <button className="icon-button" aria-label="Close observation details" onClick={close}><X size={15}/></button>}</div>
    {!id ? <div className="detail-placeholder"><div className="reticle"><Crosshair size={36}/></div><span className="eyebrow">FOLLOW THE EVIDENCE</span><h3>A point. A context.<br/>A closer look.</h3><p>Select a globe marker, an observation, or a review alert to inspect its source evidence.</p><div className="mini-note"><Info size={15}/><span>Markers are satellite detections, not fire boundaries.</span></div></div> :
      error ? <p role="alert" className="inline-error">{error}</p> : !row ? <p role="status" className="detail-loading">Loading observation evidence…</p> :
      <div className="detail-body">
        <div className="detail-badges"><CategoryBadge category={row.predicted_class}/><RiskBadge band={row.risk_band}/></div>
        <div className="id-block"><Fingerprint size={15}/><span>{row.hotspot_id}</span></div>
        <div className="score-block"><span className="eyebrow">HUMAN-REVIEW PRIORITY</span><div><strong>{numberText(row.risk_score, 2)}</strong><span>/ 100</span></div><p>Deterministic score · not a probability</p></div>
        <dl className="evidence-grid">
          <div><dt>FRP</dt><dd>{numberText(row.frp)} <small>MW</small></dd></div>
          <div><dt>Persistence</dt><dd>{row.persistence_count_30d} <small>days / 30d</small></dd></div>
          <div><dt>Sensor confidence</dt><dd>{CONFIDENCE[row.confidence]}</dd></div>
          <div><dt>Observation</dt><dd>{row.day_night === 'N' ? 'Night' : 'Day'}</dd></div>
          <div><dt>Latitude</dt><dd>{row.latitude.toFixed(5)}°</dd></div>
          <div><dt>Longitude</dt><dd>{row.longitude.toFixed(5)}°</dd></div>
        </dl>
        <p className="observation-time">{observationTime(row)}</p>
        <div className="evidence-section"><h3>Evidence behind the score</h3><p>{row.explanation}</p>
          <dl className="point-list"><div><dt>FRP contribution</dt><dd>{numberText(row.frp_points, 2)} / 40</dd></div><div><dt>Persistence contribution</dt><dd>{numberText(row.persistence_points, 2)} / 30</dd></div><div><dt>Sensor confidence contribution</dt><dd>{numberText(row.confidence_points, 2)} / 20</dd></div><div><dt>Night observation contribution</dt><dd>{numberText(row.night_points, 2)} / 10</dd></div></dl>
          <p className="small-note">Primary driver: {row.primary_risk_driver.replaceAll('_', ' ')}.</p>
        </div>
        <div className="evidence-section"><h3>Geographic context</h3><p>Centre-pixel land cover: <b>{row.land_cover_class}</b></p><p>Nearest mapped industry: <b>{row.distance_to_industrial_km === null ? 'Not available' : numberText(row.distance_to_industrial_km, 3) + ' km'}</b></p><p>Brightness: {numberText(row.brightness)} K</p></div>
        <p className="mini-note"><Info size={16}/><span>Evidence-linked review context. These are proxy categories, not verified causes or dispatch recommendations. Sensor confidence is not model probability.</span></p>
      </div>}
  </aside>
}
