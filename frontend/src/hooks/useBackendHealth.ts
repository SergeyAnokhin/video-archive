import { useEffect, useState } from 'react'
import { tryApi } from '../api/client'
import type { HealthResponse } from '../types/api'

export type BackendHealth = 'checking' | 'online' | 'offline'

const POLL_INTERVAL_MS = 5000

/** Live backend-reachability signal for the top-bar status dot (chat request
 * 2026-07-19), independent of `useBackendStatus.ts`'s one-shot app-info load
 * used by `BackendStatusPanel`. Polls `/api/health` via `tryApi` (never
 * throws) so a failed poll just flips the dot red instead of crashing. */
export function useBackendHealth(): BackendHealth {
  const [health, setHealth] = useState<BackendHealth>('checking')

  useEffect(() => {
    let cancelled = false

    async function check() {
      const result = await tryApi<HealthResponse>('/api/health')
      if (!cancelled) setHealth(result ? 'online' : 'offline')
    }

    void check()
    const timer = window.setInterval(() => void check(), POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  return health
}
