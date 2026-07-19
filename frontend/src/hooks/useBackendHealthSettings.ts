import { useEffect, useState } from 'react'
import { tryApi } from '../api/client'
import type { BackendHealthSettings } from '../types/api'
import { DEFAULT_HEALTH_TIMEOUTS, type BackendHealthTimeouts } from './useBackendHealth'

/** One-shot load of the user-configured slow/offline timeouts (Settings ->
 * Network) for `useBackendHealth()`. Starts from the same defaults the
 * backend seeds so the dot behaves sensibly before this resolves, then
 * switches over once the real settings load (best-effort -- `tryApi`
 * resolves `null` on failure, so a load error just keeps the defaults). */
export function useBackendHealthSettings(): BackendHealthTimeouts {
  const [timeouts, setTimeouts] = useState<BackendHealthTimeouts>(DEFAULT_HEALTH_TIMEOUTS)

  useEffect(() => {
    let cancelled = false
    tryApi<BackendHealthSettings>('/api/backend-health-settings').then((data) => {
      if (!data || cancelled) return
      setTimeouts({
        slowTimeoutMs: data.slow_timeout_seconds * 1000,
        offlineTimeoutMs: data.offline_timeout_seconds * 1000,
      })
    })
    return () => {
      cancelled = true
    }
  }, [])

  return timeouts
}
