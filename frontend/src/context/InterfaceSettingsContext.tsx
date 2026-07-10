import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import i18n, { persistLanguage, SUPPORTED_LANGUAGES, type SupportedLanguage } from '../i18n'
import { THEME_PRESETS, type InterfaceSettings, type ThemePreset } from '../types/api'

const THEME_STORAGE_KEY = 'video-archive:theme'

function detectInitialTheme(): ThemePreset {
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY)
  return (THEME_PRESETS as readonly string[]).includes(stored ?? '') ? (stored as ThemePreset) : 'strict'
}

function applyTheme(theme: ThemePreset) {
  document.documentElement.dataset.theme = theme
}

interface InterfaceSettingsContextValue {
  theme: ThemePreset
  setTheme: (theme: ThemePreset) => void
  language: SupportedLanguage
  setLanguage: (language: SupportedLanguage) => void
}

const InterfaceSettingsContext = createContext<InterfaceSettingsContextValue | undefined>(undefined)

function persistToBackend(theme: ThemePreset, language: SupportedLanguage) {
  void fetch('/api/interface-settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ language, theme_preset: theme }),
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
    persistToBackend(next, language)
  }

  function setLanguage(next: SupportedLanguage) {
    setLanguageState(next)
    void i18n.changeLanguage(next)
    persistLanguage(next)
    persistToBackend(theme, next)
  }

  return (
    <InterfaceSettingsContext.Provider value={{ theme, setTheme, language, setLanguage }}>
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
