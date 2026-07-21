import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

// Persisted to localStorage (user request) across app restarts: which of the
// two preview-stylization profiles (InterfaceSettingsContext's
// `previewProfiles`) is currently applied to thumbnails across the app.
// Previously this boolean gated whether the thumbnail image rendered at all
// (falling back to a folder/film icon); now the image always renders and
// this only picks which CSS `filter` (profile A vs B) is applied, via the
// `data-preview-profile` attribute consumed by LibraryView.css.
interface PreviewVisibilityContextValue {
  previewsVisible: boolean
  toggle: () => void
}

const PreviewVisibilityContext = createContext<PreviewVisibilityContextValue | null>(null)

const STORAGE_KEY = 'video-archive:previews-visible'

function getInitialPreviewsVisible(): boolean {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    return stored === null ? true : stored === 'true'
  } catch {
    return true
  }
}

function applyPreviewProfileAttr(previewsVisible: boolean) {
  document.documentElement.dataset.previewProfile = previewsVisible ? 'a' : 'b'
}

export function PreviewVisibilityProvider({ children }: { children: ReactNode }) {
  const [previewsVisible, setPreviewsVisible] = useState(getInitialPreviewsVisible)

  // Keyed on previewsVisible so it also runs on mount -- fixes the previous
  // version never applying the attribute until the first toggle click.
  useEffect(() => {
    applyPreviewProfileAttr(previewsVisible)
    try {
      window.localStorage.setItem(STORAGE_KEY, String(previewsVisible))
    } catch {
      // Private browsing / quota exceeded -- falls back to session-only.
    }
  }, [previewsVisible])

  const value = useMemo(
    () => ({
      previewsVisible,
      toggle: () => setPreviewsVisible((visible) => !visible),
    }),
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
