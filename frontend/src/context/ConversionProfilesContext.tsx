import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import type { ConversionProfile } from '../types/api'

interface ConversionProfilesContextValue {
  profiles: ConversionProfile[]
  loading: boolean
  refresh: () => Promise<void>
}

const ConversionProfilesContext = createContext<ConversionProfilesContextValue | null>(null)

export function ConversionProfilesProvider({ children }: { children: ReactNode }) {
  const [profiles, setProfiles] = useState<ConversionProfile[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/conversion-profiles')
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`)
      }
      const data: { profiles: ConversionProfile[] } = await res.json()
      setProfiles(data.profiles)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const value = useMemo(() => ({ profiles, loading, refresh }), [profiles, loading, refresh])

  return (
    <ConversionProfilesContext.Provider value={value}>
      {children}
    </ConversionProfilesContext.Provider>
  )
}

export function useConversionProfiles(): ConversionProfilesContextValue {
  const context = useContext(ConversionProfilesContext)
  if (!context) {
    throw new Error('useConversionProfiles must be used within ConversionProfilesProvider')
  }
  return context
}
