import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { HealthResponse } from '../types/api'

export type BackendHealth = 'checking' | 'online' | 'slow' | 'offline'

export interface BackendHealthTimeouts {
  /** How long a poll waits for `/api/health` before going 'slow'. */
  slowTimeoutMs: number
  /** How much longer the 'slow'-state retry waits before giving up and
   * going 'offline'. */
  offlineTimeoutMs: number
}

// Matches `backend_health_settings.py`'s defaults -- used until
// `useBackendHealthSettings()` resolves the user's configured values (chat
// request 2026-07-19 follow-up: "let me configure these timeouts").
export const DEFAULT_HEALTH_TIMEOUTS: BackendHealthTimeouts = {
  slowTimeoutMs: 5000,
  offlineTimeoutMs: 10000,
}

const POLL_INTERVAL_MS = 5000

type ProbeResult = 'ok' | 'timeout' | 'error'

async function probe(timeoutMs: number): Promise<ProbeResult> {
  try {
    await api<HealthResponse>('/api/health', { timeoutMs })
    return 'ok'
  } catch (err) {
    // AbortError means our own timeout fired -- the backend might just be
    // busy, not down, so it's not a definitive failure. Anything else
    // (connection refused, a non-2xx ApiError, ...) is.
    return err instanceof DOMException && err.name === 'AbortError' ? 'timeout' : 'error'
  }
}

/** Live backend-reachability signal for the top-bar status dot (chat request
 * 2026-07-19), independent of `useBackendStatus.ts`'s one-shot app-info load
 * used by `BackendStatusPanel`. Distinguishes a slow-but-alive backend (e.g.
 * mid-conversion, pegging the CPU) from an actually unreachable one: a poll
 * that doesn't answer within `slowTimeoutMs` goes 'slow' and gets one retry
 * with an `offlineTimeoutMs` ceiling before finally going 'offline'; a
 * definitive failure (connection refused, non-2xx) skips straight to
 * 'offline' since waiting out a retry there wouldn't help. Both timeouts are
 * user-configurable (Settings -> Network, `backend_health_settings.py`). */
export function useBackendHealth(timeouts: BackendHealthTimeouts = DEFAULT_HEALTH_TIMEOUTS): BackendHealth {
  const { slowTimeoutMs, offlineTimeoutMs } = timeouts
  const [health, setHealth] = useState<BackendHealth>('checking')

  useEffect(() => {
    let cancelled = false
    let timer: number

    async function cycle() {
      const first = await probe(slowTimeoutMs)
      if (cancelled) return

      if (first === 'ok') {
        setHealth('online')
      } else if (first === 'error') {
        setHealth('offline')
      } else {
        setHealth('slow')
        const retry = await probe(offlineTimeoutMs)
        if (cancelled) return
        setHealth(retry === 'ok' ? 'online' : 'offline')
      }

      if (!cancelled) {
        timer = window.setTimeout(() => void cycle(), POLL_INTERVAL_MS)
      }
    }

    void cycle()
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [slowTimeoutMs, offlineTimeoutMs])

  return health
}
