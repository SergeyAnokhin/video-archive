import { useEffect, useState } from 'react'
import { api } from '../api/client'
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
        const [health, appInfo] = await Promise.all([
          api<HealthResponse>('/api/health'),
          api<AppInfoResponse>('/api/app/info'),
        ])

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
