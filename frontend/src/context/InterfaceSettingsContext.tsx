import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import i18n, { persistLanguage, SUPPORTED_LANGUAGES, type SupportedLanguage } from '../i18n'
import { THEME_PRESETS, type InterfaceSettings, type ThemePreset } from '../types/api'

const THEME_STORAGE_KEY = 'video-archive:theme'
const PREVIEW_SATURATION_STORAGE_KEY = 'video-archive:preview-saturation'

function detectInitialTheme(): ThemePreset {
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY)
  return (THEME_PRESETS as readonly string[]).includes(stored ?? '') ? (stored as ThemePreset) : 'strict'
}

function detectInitialPreviewSaturation(): number {
  const stored = Number(window.localStorage.getItem(PREVIEW_SATURATION_STORAGE_KEY))
  return Number.isFinite(stored) && stored >= 0 && stored <= 100 ? stored : 100
}

function applyTheme(theme: ThemePreset) {
  document.documentElement.dataset.theme = theme
}

function applyPreviewSaturation(saturation: number) {
  document.documentElement.style.setProperty('--preview-saturation', String(saturation / 100))
}

interface InterfaceSettingsContextValue {
  theme: ThemePreset
  setTheme: (theme: ThemePreset) => void
  language: SupportedLanguage
  setLanguage: (language: SupportedLanguage) => void
  previewSaturation: number
  setPreviewSaturation: (saturation: number) => void
}

const InterfaceSettingsContext = createContext<InterfaceSettingsContextValue | undefined>(undefined)

function persistToBackend(theme: ThemePreset, language: SupportedLanguage, previewSaturation: number) {
  void fetch('/api/interface-settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ language, theme_preset: theme, preview_saturation: previewSaturation }),
  })
}

export function InterfaceSettingsProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemePreset>(() => {
    const initial = detectInitialTheme()
    applyTheme(initial)
    return initial
  })
  const [language, setLanguageState] = useState<SupportedLanguage>(
    (i18n.resolvedLanguage as SupportedLanguage) ?? 'en',
  )
  const [previewSaturation, setPreviewSaturationState] = useState<number>(() => {
    const initial = detectInitialPreviewSaturation()
    applyPreviewSaturation(initial)
    return initial
  })

  // Backend-persisted preferences are the source of truth once loaded; the
  // localStorage/browser-locale guess applied synchronously above just avoids
  // a flash of the wrong theme/language before this request resolves.
  useEffect(() => {
    let cancelled = false
    fetch('/api/interface-settings')
      .then((res) => (res.ok ? (res.json() as Promise<InterfaceSettings>) : null))
      .then((data) => {
        if (cancelled || !data) return
        if (data.theme_preset && data.theme_preset !== theme) {
          setThemeState(data.theme_preset)
          applyTheme(data.theme_preset)
          window.localStorage.setItem(THEME_STORAGE_KEY, data.theme_preset)
        }
        if (
          data.language &&
          (SUPPORTED_LANGUAGES as readonly string[]).includes(data.language) &&
          data.language !== i18n.resolvedLanguage
        ) {
          setLanguageState(data.language)
          void i18n.changeLanguage(data.language)
          persistLanguage(data.language)
        }
        if (data.preview_saturation != null && data.preview_saturation !== previewSaturation) {
          setPreviewSaturationState(data.preview_saturation)
          applyPreviewSaturation(data.preview_saturation)
          window.localStorage.setItem(PREVIEW_SATURATION_STORAGE_KEY, String(data.preview_saturation))
        }
      })
      .catch(() => {
        // Best-effort sync; localStorage/browser-locale detection already applied above.
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function setTheme(next: ThemePreset) {
    setThemeState(next)
    applyTheme(next)
    window.localStorage.setItem(THEME_STORAGE_KEY, next)
    persistToBackend(next, language, previewSaturation)
  }

  function setLanguage(next: SupportedLanguage) {
    setLanguageState(next)
    void i18n.changeLanguage(next)
    persistLanguage(next)
    persistToBackend(theme, next, previewSaturation)
  }

  function setPreviewSaturation(next: number) {
    setPreviewSaturationState(next)
    applyPreviewSaturation(next)
    window.localStorage.setItem(PREVIEW_SATURATION_STORAGE_KEY, String(next))
    persistToBackend(theme, language, next)
  }

  return (
    <InterfaceSettingsContext.Provider
      value={{ theme, setTheme, language, setLanguage, previewSaturation, setPreviewSaturation }}
    >
      {children}
    </InterfaceSettingsContext.Provider>
  )
}

export function useInterfaceSettings() {
  const ctx = useContext(InterfaceSettingsContext)
  if (!ctx) {
    throw new Error('useInterfaceSettings must be used within InterfaceSettingsProvider')
  }
  return ctx
}
