import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import type { JobItem, JobSummary } from '../types/api'

interface JobsContextValue {
  jobs: JobSummary[]
  activeJob: JobSummary | null
  activeJobItems: JobItem[]
  refresh: () => Promise<void>
}

const JobsContext = createContext<JobsContextValue | null>(null)

const POLL_INTERVAL_MS = 1500

export function JobsProvider({ children }: { children: ReactNode }) {
  const [jobs, setJobs] = useState<JobSummary[]>([])
  const [activeJobItems, setActiveJobItems] = useState<JobItem[]>([])

  async function refresh() {
    try {
      const res = await fetch('/api/jobs?limit=200')
      if (!res.ok) return
      const data: { jobs: JobSummary[] } = await res.json()
      setJobs(data.jobs)
    } catch {
      // Polling failure is transient; keep the last known jobs list.
    }
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
      try {
        const res = await fetch(`/api/jobs/${activeJob!.id}/items`)
        if (!res.ok) return
        const data: { items: JobItem[] } = await res.json()
        if (!cancelled) {
          setActiveJobItems(data.items)
        }
      } catch {
        // Polling failure is transient; keep the last known items.
      }
    }

    void loadItems()
    const timer = window.setInterval(() => void loadItems(), POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [activeJob?.id])

  const value = useMemo(
    () => ({ jobs, activeJob, activeJobItems, refresh }),
    [jobs, activeJob, activeJobItems],
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
