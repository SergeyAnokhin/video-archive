// @vitest-environment jsdom
//
// State-machine coverage for the busy-vs-down distinction (chat request
// 2026-07-19 follow-up): a slow poll (AbortError -- our own timeout fired)
// must go through 'slow' with a longer retry before ever reaching
// 'offline', while a definitive failure (network error, non-2xx) skips
// straight to 'offline'. Mocks `api/client.ts`'s `api()` directly rather
// than stubbing `fetch` -- what's under test is the branching on the
// *outcome* of a poll, not `fetchWithTimeout`'s abort plumbing.
import { cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useBackendHealth } from './useBackendHealth'
import * as apiClient from '../api/client'

vi.mock('../api/client', () => ({ api: vi.fn() }))
const mockedApi = vi.mocked(apiClient.api)

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('useBackendHealth', () => {
  it('passes the configured slow/offline timeouts through to each poll', async () => {
    // Regression: Settings -> Network lets the user tune these (chat
    // request 2026-07-19 follow-up); a request built with the wrong
    // timeout would silently misreport "slow" as "offline" or vice versa.
    mockedApi
      .mockRejectedValueOnce(new DOMException('aborted', 'AbortError'))
      .mockResolvedValueOnce({ status: 'ok' })
    renderHook(() => useBackendHealth({ slowTimeoutMs: 1234, offlineTimeoutMs: 5678 }))
    await waitFor(() => expect(mockedApi).toHaveBeenCalledTimes(2))
    expect(mockedApi).toHaveBeenNthCalledWith(1, '/api/health', { timeoutMs: 1234 })
    expect(mockedApi).toHaveBeenNthCalledWith(2, '/api/health', { timeoutMs: 5678 })
  })

  it('starts checking, then goes online on a fast successful poll', async () => {
    mockedApi.mockResolvedValue({ status: 'ok' })
    const { result } = renderHook(() => useBackendHealth())
    expect(result.current).toBe('checking')
    await waitFor(() => expect(result.current).toBe('online'))
  })

  it('goes offline immediately on a definitive error, without an intermediate slow state', async () => {
    mockedApi.mockRejectedValue(new TypeError('Failed to fetch'))
    const { result } = renderHook(() => useBackendHealth())
    await waitFor(() => expect(result.current).toBe('offline'))
  })

  it('goes slow on a timeout, then online once the retry succeeds', async () => {
    // The retry resolves on a real macrotask (not the same microtask tick
    // as the first call) so the intermediate 'slow' render is observable --
    // otherwise both probes settle before `waitFor`'s first poll ever runs.
    mockedApi
      .mockRejectedValueOnce(new DOMException('aborted', 'AbortError'))
      .mockImplementationOnce(() => new Promise((resolve) => setTimeout(() => resolve({ status: 'ok' }), 150)))
    const { result } = renderHook(() => useBackendHealth())
    await waitFor(() => expect(result.current).toBe('slow'))
    await waitFor(() => expect(result.current).toBe('online'))
  })

  it('goes offline if the slow-state retry also times out', async () => {
    mockedApi
      .mockRejectedValueOnce(new DOMException('aborted', 'AbortError'))
      .mockImplementationOnce(
        () => new Promise((_resolve, reject) => setTimeout(() => reject(new DOMException('aborted', 'AbortError')), 150)),
      )
    const { result } = renderHook(() => useBackendHealth())
    await waitFor(() => expect(result.current).toBe('slow'))
    await waitFor(() => expect(result.current).toBe('offline'))
  })
})
