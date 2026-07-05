import { useEffect, useState } from 'react'
import type { AppInfoResponse, HealthResponse } from '../types/api'

export type BackendStatusState =
  | { phase: 'loading' }
  | { phase: 'error'; message: string }
  | { phase: 'ready'; health: HealthResponse; appInfo: AppInfoResponse }

export function useBackendStatus(): BackendStatusState {
  const [state, setState] = useState<BackendStatusState>({ phase: 'loading' })

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const [healthRes, appInfoRes] = await Promise.all([
          fetch('/api/health'),
          fetch('/api/app/info'),
        ])

        if (!healthRes.ok || !appInfoRes.ok) {
          throw new Error(`HTTP ${healthRes.status}/${appInfoRes.status}`)
        }

        const health: HealthResponse = await healthRes.json()
        const appInfo: AppInfoResponse = await appInfoRes.json()

        if (!cancelled) {
          setState({ phase: 'ready', health, appInfo })
        }
      } catch (err) {
        if (!cancelled) {
          setState({
            phase: 'error',
            message: err instanceof Error ? err.message : String(err),
          })
        }
      }
    }

    load()

    return () => {
      cancelled = true
    }
  }, [])

  return state
}
