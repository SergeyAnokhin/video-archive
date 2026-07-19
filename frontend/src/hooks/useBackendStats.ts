import { useEffect, useRef, useState } from 'react'
import { tryApi } from '../api/client'
import type { SystemStatsResponse } from '../types/api'
import { computeNetworkRate, type ByteSample } from '../utils/backendStats'
import type { BackendHealth } from './useBackendHealth'

export interface BackendStats {
  cpuPercent: number
  memoryRssBytes: number
  memoryPercent: number
  networkBytesPerSec: number
}

const POLL_INTERVAL_MS = 5000

/** Resource-usage samples for the top-bar meter (chat request 2026-07-19).
 * Only polls `/api/system/stats` while `health` is `'online'` -- no point
 * hitting the backend for stats when it's already known unreachable. */
export function useBackendStats(health: BackendHealth): BackendStats | null {
  const [stats, setStats] = useState<BackendStats | null>(null)
  const lastSample = useRef<ByteSample | null>(null)

  useEffect(() => {
    if (health !== 'online') {
      setStats(null)
      lastSample.current = null
      return
    }

    let cancelled = false

    async function poll() {
      const data = await tryApi<SystemStatsResponse>('/api/system/stats')
      if (!data || cancelled) return

      const sample: ByteSample = { bytes: data.smb_bytes_transferred_total, timestampSeconds: data.timestamp }
      const networkBytesPerSec = computeNetworkRate(lastSample.current, sample)
      lastSample.current = sample

      setStats({
        cpuPercent: data.cpu_percent,
        memoryRssBytes: data.memory_rss_bytes,
        memoryPercent: data.memory_percent,
        networkBytesPerSec,
      })
    }

    void poll()
    const timer = window.setInterval(() => void poll(), POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [health])

  return stats
}
