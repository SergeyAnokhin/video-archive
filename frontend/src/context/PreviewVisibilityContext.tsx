import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'

// Session-only (not persisted, matches the prior "hide previews" toggle's
// lifetime): which of the two preview-stylization profiles
// (InterfaceSettingsContext's `previewProfiles`) is currently applied to
// thumbnails across the app. Previously this boolean gated whether the
// thumbnail image rendered at all (falling back to a folder/film icon);
// now the image always renders and this only picks which CSS `filter`
// (profile A vs B) is applied, via the `data-preview-profile` attribute
// consumed by LibraryView.css.
interface PreviewVisibilityContextValue {
  previewsVisible: boolean
  toggle: () => void
}

const PreviewVisibilityContext = createContext<PreviewVisibilityContextValue | null>(null)

function applyPreviewProfileAttr(previewsVisible: boolean) {
  document.documentElement.dataset.previewProfile = previewsVisible ? 'a' : 'b'
}

export function PreviewVisibilityProvider({ children }: { children: ReactNode }) {
  const [previewsVisible, setPreviewsVisible] = useState(true)

  const value = useMemo(
    () => ({
      previewsVisible,
      toggle: () =>
        setPreviewsVisible((visible) => {
          const next = !visible
          applyPreviewProfileAttr(next)
          return next
        }),
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
