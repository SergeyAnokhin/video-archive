import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchWithTimeout } from './fetchWithTimeout'

// `fetchWithTimeout()` is the defensive client-side ceiling on Tag Lab's
// /prepare and /run calls (user request -- the modal must never wait on
// "Waiting for the model's response..." forever). Covers both branches: a
// normal response beats the timeout, and the timeout aborts a fetch that
// never settles.
describe('fetchWithTimeout', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('resolves with the response when fetch completes before the timeout', async () => {
    const response = new Response('{}', { status: 200 })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))

    const result = await fetchWithTimeout('/api/x', {}, 1000)

    expect(result).toBe(response)
  })

  it('rejects with an AbortError once the timeout elapses before fetch settles', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(
        (_url: string, options: RequestInit) =>
          new Promise((_resolve, reject) => {
            options.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
          }),
      ),
    )

    const pending = fetchWithTimeout('/api/x', {}, 1000)
    const assertion = expect(pending).rejects.toMatchObject({ name: 'AbortError' })
    await vi.advanceTimersByTimeAsync(1000)
    await assertion
  })
})
