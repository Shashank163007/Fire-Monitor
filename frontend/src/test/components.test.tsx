import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CategoryBadge, RiskBadge } from '../components/Badges'
import { EmptyState, ErrorState, LoadingState } from '../components/Status'
import { FilterPanel } from '../components/FilterPanel'
import { DetailPanel } from '../components/DetailPanel'
import { EMPTY_FILTERS } from '../state/filters'
import { row } from './fixtures'
describe('accessible states and data presentation', () => {
  it('names all categories as weak-label candidates or unknown', () => {
    render(<><CategoryBadge category="industrial"/><CategoryBadge category="wildfire"/><CategoryBadge category="unknown"/></>)
    expect(screen.getByText('Industrial candidate')).toHaveStyle({ color: '#f5a45d' })
    expect(screen.getByText('Wildfire candidate')).toHaveStyle({ color: '#f06b70' })
    expect(screen.getByText('Unknown')).toBeVisible()
  })
  it.each(['critical', 'high', 'moderate', 'low'] as const)('displays %s priority without probability wording', band => {
    render(<RiskBadge band={band}/>)
    expect(screen.getByText(new RegExp(band + ' priority', 'i'))).toBeVisible()
    expect(screen.queryByText(/probability/i)).not.toBeInTheDocument()
  })
  it('explains empty results and offers a reset', async () => {
    const reset = vi.fn(); render(<EmptyState reset={reset}/>)
    expect(screen.getByRole('status')).toHaveTextContent('No matching observations')
    await userEvent.click(screen.getByRole('button', { name: 'Reset filters' })); expect(reset).toHaveBeenCalledOnce()
  })
  it('shows explicit offline context and retry rather than cached metrics', async () => {
    const retry = vi.fn(); render(<ErrorState offline message="Local API unavailable." retry={retry}/>)
    expect(screen.getByRole('alert')).toHaveTextContent('Previously loaded data is hidden')
    await userEvent.click(screen.getByRole('button', { name: /Reconnect/ })); expect(retry).toHaveBeenCalledOnce()
  })
  it('separates response errors from offline errors', () => {
    render(<ErrorState offline={false} message="Invalid snapshot response." retry={() => {}}/>)
    expect(screen.getByRole('alert')).toHaveTextContent('The snapshot could not be loaded')
  })
  it('shows a loading status without made-up counters', () => {
    render(<LoadingState/>); expect(screen.getByRole('status')).toHaveTextContent('Connecting')
    expect(screen.queryByText('674')).not.toBeInTheDocument()
  })
  it('submits filters and resets the active count', async () => {
    const apply = vi.fn(); render(<FilterPanel filters={EMPTY_FILTERS} onApply={apply}/>)
    await userEvent.selectOptions(screen.getByLabelText('Context category'), 'industrial')
    await userEvent.click(screen.getByRole('button', { name: /Apply filters/ }))
    expect(apply).toHaveBeenLastCalledWith({ ...EMPTY_FILTERS, predicted_class: 'industrial' })
    await userEvent.click(screen.getByRole('button', { name: 'Reset filters' }))
    expect(apply).toHaveBeenLastCalledWith(EMPTY_FILTERS)
  })
  it('distinguishes sensor confidence from probability and shows the exact API explanation', () => {
    render(<DetailPanel id={row.hotspot_id} row={row} close={() => {}}/>)
    expect(screen.getByText(row.explanation)).toBeVisible()
    expect(screen.getByText('Sensor confidence')).toBeVisible()
    expect(screen.getByText('Deterministic score · not a probability')).toBeVisible()
    expect(screen.getByText(/not model probability/)).toBeVisible()
    expect(screen.queryByText('null')).not.toBeInTheDocument()
  })
})
