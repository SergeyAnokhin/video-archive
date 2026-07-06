import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import type { SourceConfig } from '../types/api'

interface SourceContextValue {
  source: SourceConfig | null
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  setSource: (source: SourceConfig) => void
}

const SourceContext = createContext<SourceContextValue | null>(null)

export function SourceProvider({ children }: { children: ReactNode }) {
  const [source, setSourceState] = useState<SourceConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/source')
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`)
      }
      const data: SourceConfig | null = await res.json()
      setSourceState(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const value = useMemo(
    () => ({ source, loading, error, refresh, setSource: setSourceState }),
    [source, loading, error, refresh],
  )

  return <SourceContext.Provider value={value}>{children}</SourceContext.Provider>
}

export function useSource(): SourceContextValue {
  const context = useContext(SourceContext)
  if (!context) {
    throw new Error('useSource must be used within SourceProvider')
  }
  return context
}
