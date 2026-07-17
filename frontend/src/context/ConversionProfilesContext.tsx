import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { api } from '../api/client'
import type { ConversionProfile } from '../types/api'

interface ConversionProfilesContextValue {
  profiles: ConversionProfile[]
  loading: boolean
  refresh: () => Promise<void>
  ensureDefaultProfile: (name: string) => Promise<ConversionProfile>
}

// Baseline used to seed a "starter" profile when none exist yet, so Convert/
// Tune always have something to work from instead of blocking on an empty
// profile list.
const FALLBACK_PROFILE_DEFAULTS = {
  video_codec: 'h265',
  container: 'mp4',
  max_dimension: 1024,
  crf: 28,
  drop_audio: true,
}

const ConversionProfilesContext = createContext<ConversionProfilesContextValue | null>(null)

export function ConversionProfilesProvider({ children }: { children: ReactNode }) {
  const [profiles, setProfiles] = useState<ConversionProfile[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api<{ profiles: ConversionProfile[] }>('/api/conversion-profiles')
      setProfiles(data.profiles)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const ensureDefaultProfile = useCallback(
    async (name: string): Promise<ConversionProfile> => {
      const data = await api<{ profiles: ConversionProfile[] }>('/api/conversion-profiles')
      const existing = data.profiles.find((p) => p.is_default) ?? data.profiles[0]
      if (existing) {
        return existing
      }
      const created = await api<ConversionProfile>('/api/conversion-profiles', {
        method: 'POST',
        body: { name, is_default: true, ...FALLBACK_PROFILE_DEFAULTS },
      })
      await refresh()
      return created
    },
    [refresh],
  )

  const value = useMemo(
    () => ({ profiles, loading, refresh, ensureDefaultProfile }),
    [profiles, loading, refresh, ensureDefaultProfile],
  )

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
