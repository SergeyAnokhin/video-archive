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
import type { Tag } from '../types/api'

interface TagsContextValue {
  tags: Tag[]
  loading: boolean
  refresh: () => Promise<void>
}

const TagsContext = createContext<TagsContextValue | null>(null)

export function TagsProvider({ children }: { children: ReactNode }) {
  const [tags, setTags] = useState<Tag[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api<{ tags: Tag[] }>('/api/tags')
      setTags(data.tags)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const value = useMemo(() => ({ tags, loading, refresh }), [tags, loading, refresh])

  return <TagsContext.Provider value={value}>{children}</TagsContext.Provider>
}

export function useTags(): TagsContextValue {
  const context = useContext(TagsContext)
  if (!context) {
    throw new Error('useTags must be used within TagsProvider')
  }
  return context
}
