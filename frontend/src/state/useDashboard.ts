import { useEffect, useState } from 'react'
import { api, ApiError } from '../api/client'
import type { Snapshot } from '../api/client'
import type { Hotspot } from '../api/schema'
import type { QueryState } from './filters'

type State = { phase: 'loading' } | { phase: 'error'; error: ApiError } | { phase: 'ready'; data: Snapshot }
export function useDashboard(query: QueryState, revision: number) {
  const [state, setState] = useState<State>({ phase: 'loading' })
  useEffect(() => {
    const controller = new AbortController()
    setState({ phase: 'loading' })
    api.snapshot(query, controller.signal)
      .then(data => { if (!controller.signal.aborted) setState({ phase: 'ready', data }) })
      .catch(error => {
        if (!controller.signal.aborted) setState({ phase: 'error', error: error instanceof ApiError ? error : new ApiError('Unable to load snapshot.', 'contract') })
      })
    const heartbeat = window.setInterval(() => {
      api.health(controller.signal).catch(error => {
        if (!controller.signal.aborted) setState({ phase: 'error', error: error instanceof ApiError ? error : new ApiError('Local API unavailable.', 'offline') })
      })
    }, 15000)
    return () => { controller.abort(); window.clearInterval(heartbeat) }
  }, [query, revision])
  return state
}
export function useHotspot(id: string | null) {
  const [detail, setDetail] = useState<{ id: string; row?: Hotspot; error?: string } | null>(null)
  useEffect(() => {
    if (!id) return
    const controller = new AbortController()
    api.detail(id, controller.signal)
      .then(row => { if (!controller.signal.aborted) setDetail({ id, row }) })
      .catch(error => { if (!controller.signal.aborted) setDetail({ id, error: error instanceof Error ? error.message : 'Unable to load observation.' }) })
    return () => controller.abort()
  }, [id])
  return detail?.id === id ? detail : null
}
