import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'

interface PreviewVisibilityContextValue {
  previewsVisible: boolean
  toggle: () => void
}

const PreviewVisibilityContext = createContext<PreviewVisibilityContextValue | null>(null)

export function PreviewVisibilityProvider({ children }: { children: ReactNode }) {
  const [previewsVisible, setPreviewsVisible] = useState(true)

  const value = useMemo(
    () => ({ previewsVisible, toggle: () => setPreviewsVisible((visible) => !visible) }),
    [previewsVisible],
  )

  return (
    <PreviewVisibilityContext.Provider value={value}>
      {children}
    </PreviewVisibilityContext.Provider>
  )
}

export function usePreviewVisibility(): PreviewVisibilityContextValue {
  const context = useContext(PreviewVisibilityContext)
  if (!context) {
    throw new Error('usePreviewVisibility must be used within PreviewVisibilityProvider')
  }
  return context
}
