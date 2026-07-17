import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { tryApi } from '../api/client'
import type { JobItem, JobSummary } from '../types/api'

interface JobsContextValue {
  jobs: JobSummary[]
  activeJob: JobSummary | null
  activeJobItems: JobItem[]
  /** Items for every currently running/paused job, keyed by job id -- unlike
   * `activeJob`/`activeJobItems` (kept for the single-job top-bar activity
   * indicator), this covers every lane at once so `JobsModal.tsx` can show
   * live per-item progress on more than one card, now that a CPU-bound and
   * a network-bound job can run concurrently (post-V1 user request). */
  jobItemsById: Record<string, JobItem[]>
  refresh: () => Promise<void>
}

const JobsContext = createContext<JobsContextValue | null>(null)

const POLL_INTERVAL_MS = 1500

export function JobsProvider({ children }: { children: ReactNode }) {
  const [jobs, setJobs] = useState<JobSummary[]>([])
  const [activeJobItems, setActiveJobItems] = useState<JobItem[]>([])
  const [jobItemsById, setJobItemsById] = useState<Record<string, JobItem[]>>({})

  async function refresh() {
    // Polling failure is transient (tryApi resolves null); keep the last known jobs list.
    const data = await tryApi<{ jobs: JobSummary[] }>('/api/jobs?limit=200')
    if (data) setJobs(data.jobs)
  }

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => void refresh(), POLL_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [])

  const activeJob =
    jobs.find((job) => job.status === 'running') ??
    jobs.find((job) => job.status === 'queued') ??
    null

  useEffect(() => {
    if (!activeJob) {
      setActiveJobItems([])
      return
    }

    let cancelled = false

    async function loadItems() {
      // Polling failure is transient (tryApi resolves null); keep the last known items.
      const data = await tryApi<{ items: JobItem[] }>(`/api/jobs/${activeJob!.id}/items`)
      if (data && !cancelled) {
        setActiveJobItems(data.items)
      }
    }

    void loadItems()
    const timer = window.setInterval(() => void loadItems(), POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [activeJob?.id])

  const trackedJobIds = jobs
    .filter((job) => job.status === 'running' || job.status === 'paused')
    .map((job) => job.id)
  const trackedKey = trackedJobIds.slice().sort().join(',')

  useEffect(() => {
    if (trackedJobIds.length === 0) {
      setJobItemsById({})
      return
    }

    let cancelled = false

    async function loadAllItems() {
      const entries = await Promise.all(
        trackedJobIds.map(async (id) => {
          const data = await tryApi<{ items: JobItem[] }>(`/api/jobs/${id}/items`)
          return data ? ([id, data.items] as const) : null
        }),
      )
      if (cancelled) return
      setJobItemsById((prev) => {
        const next: Record<string, JobItem[]> = {}
        for (const id of trackedJobIds) {
          const found = entries.find((entry) => entry && entry[0] === id)
          next[id] = found ? found[1] : (prev[id] ?? [])
        }
        return next
      })
    }

    void loadAllItems()
    const timer = window.setInterval(() => void loadAllItems(), POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trackedKey])

  const value = useMemo(
    () => ({ jobs, activeJob, activeJobItems, jobItemsById, refresh }),
    [jobs, activeJob, activeJobItems, jobItemsById],
  )

  return <JobsContext.Provider value={value}>{children}</JobsContext.Provider>
}

export function useJobs(): JobsContextValue {
  const context = useContext(JobsContext)
  if (!context) {
    throw new Error('useJobs must be used within JobsProvider')
  }
  return context
}
