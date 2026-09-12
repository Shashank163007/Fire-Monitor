import { LoaderCircle, Radio, RefreshCw, SearchX, WifiOff } from 'lucide-react'
export function LoadingState() {
  return <div className="state-panel" role="status"><LoaderCircle className="spin" size={30}/><h2>Connecting the observation desk</h2><p>Reading the retrospective snapshot from your local API.</p></div>
}
export function ErrorState({ message, offline, retry }: { message: string; offline: boolean; retry: () => void }) {
  return <div className="state-panel error-state" role="alert"><WifiOff size={32}/><span className="eyebrow">LOCAL API / UNAVAILABLE</span>
    <h2>{offline ? 'The observation desk is offline.' : 'The snapshot could not be loaded.'}</h2>
    <p>{message}</p><p>Previously loaded data is hidden until the API reconnects.</p>
    <button className="primary-button" onClick={retry}><RefreshCw size={15}/>Reconnect to local API</button></div>
}
export function EmptyState({ reset }: { reset: () => void }) {
  return <div className="empty-state" role="status"><SearchX size={24}/><strong>No matching observations</strong><p>Try a wider date window or adjust your filters.</p><button onClick={reset}>Reset filters</button></div>
}
export function Connection({ state }: { state: 'ready' | 'loading' | 'error' }) {
  return <span className={'connection ' + state}><Radio size={13}/>{state === 'ready' ? 'Local API connected' : state === 'loading' ? 'Connecting' : 'API unavailable'}</span>
}
