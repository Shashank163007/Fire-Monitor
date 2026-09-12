import '@testing-library/jest-dom/vitest'
import { afterEach, beforeEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'
beforeEach(() => { vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Unexpected request in offline unit test')))) })
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks() })
