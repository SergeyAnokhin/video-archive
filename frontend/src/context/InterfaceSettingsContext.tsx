import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import i18n, { persistLanguage, SUPPORTED_LANGUAGES, type SupportedLanguage } from '../i18n'
import { THEME_PRESETS, type InterfaceSettings, type ThemePreset } from '../types/api'
import {
  DEFAULT_PREVIEW_PROFILE_A,
  DEFAULT_PREVIEW_PROFILE_B,
  previewFilterCss,
  type PreviewStyleProfile,
} from '../utils/previewStyle'

const THEME_STORAGE_KEY = 'video-archive:theme'
const PREVIEW_PROFILES_STORAGE_KEY = 'video-archive:preview-profiles'

type PreviewProfileKey = 'a' | 'b'

function detectInitialTheme(): ThemePreset {
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY)
  return (THEME_PRESETS as readonly string[]).includes(stored ?? '') ? (stored as ThemePreset) : 'strict'
}

function detectInitialPreviewProfiles(): Record<PreviewProfileKey, PreviewStyleProfile> {
  try {
    const raw = window.localStorage.getItem(PREVIEW_PROFILES_STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : null
    if (parsed && parsed.a && parsed.b) {
      return { a: { ...DEFAULT_PREVIEW_PROFILE_A, ...parsed.a }, b: { ...DEFAULT_PREVIEW_PROFILE_B, ...parsed.b } }
    }
  } catch {
    // fall through to defaults
  }
  return { a: DEFAULT_PREVIEW_PROFILE_A, b: DEFAULT_PREVIEW_PROFILE_B }
}

function applyTheme(theme: ThemePreset) {
  document.documentElement.dataset.theme = theme
}

function applyPreviewProfiles(profiles: Record<PreviewProfileKey, PreviewStyleProfile>) {
  document.documentElement.style.setProperty('--preview-filter-a', previewFilterCss(profiles.a))
  document.documentElement.style.setProperty('--preview-filter-b', previewFilterCss(profiles.b))
}

function profileFromSettings(data: InterfaceSettings, profile: PreviewProfileKey): PreviewStyleProfile {
  return {
    saturation: data[`profile_${profile}_saturation`],
    blur: data[`profile_${profile}_blur`],
    brightness: data[`profile_${profile}_brightness`],
    contrast: data[`profile_${profile}_contrast`],
    sepia: data[`profile_${profile}_sepia`],
    hueRotate: data[`profile_${profile}_hue_rotate`],
  }
}

function profilesEqual(a: PreviewStyleProfile, b: PreviewStyleProfile): boolean {
  return (
    a.saturation === b.saturation &&
    a.blur === b.blur &&
    a.brightness === b.brightness &&
    a.contrast === b.contrast &&
    a.sepia === b.sepia &&
    a.hueRotate === b.hueRotate
  )
}

interface InterfaceSettingsContextValue {
  theme: ThemePreset
  setTheme: (theme: ThemePreset) => void
  language: SupportedLanguage
  setLanguage: (language: SupportedLanguage) => void
  previewProfiles: Record<PreviewProfileKey, PreviewStyleProfile>
  setPreviewProfile: (profile: PreviewProfileKey, next: PreviewStyleProfile) => void
}

const InterfaceSettingsContext = createContext<InterfaceSettingsContextValue | undefined>(undefined)

function persistToBackend(
  theme: ThemePreset,
  language: SupportedLanguage,
  profiles: Record<PreviewProfileKey, PreviewStyleProfile>,
) {
  void fetch('/api/interface-settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      language,
      theme_preset: theme,
      profile_a_saturation: profiles.a.saturation,
      profile_a_blur: profiles.a.blur,
      profile_a_brightness: profiles.a.brightness,
      profile_a_contrast: profiles.a.contrast,
      profile_a_sepia: profiles.a.sepia,
      profile_a_hue_rotate: profiles.a.hueRotate,
      profile_b_saturation: profiles.b.saturation,
      profile_b_blur: profiles.b.blur,
      profile_b_brightness: profiles.b.brightness,
      profile_b_contrast: profiles.b.contrast,
      profile_b_sepia: profiles.b.sepia,
      profile_b_hue_rotate: profiles.b.hueRotate,
    }),
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
  const [previewProfiles, setPreviewProfilesState] = useState<Record<PreviewProfileKey, PreviewStyleProfile>>(() => {
    const initial = detectInitialPreviewProfiles()
    applyPreviewProfiles(initial)
    return initial
  })

  // Backend-persisted preferences are the source of truth once loaded; the
  // localStorage/browser-locale guess applied synchronously above just avoids
  // a flash of the wrong theme/language/preview style before this request
  // resolves.
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
        if (data.profile_a_saturation != null) {
          const fetched = { a: profileFromSettings(data, 'a'), b: profileFromSettings(data, 'b') }
          if (!profilesEqual(fetched.a, previewProfiles.a) || !profilesEqual(fetched.b, previewProfiles.b)) {
            setPreviewProfilesState(fetched)
            applyPreviewProfiles(fetched)
            window.localStorage.setItem(PREVIEW_PROFILES_STORAGE_KEY, JSON.stringify(fetched))
          }
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
    persistToBackend(next, language, previewProfiles)
  }

  function setLanguage(next: SupportedLanguage) {
    setLanguageState(next)
    void i18n.changeLanguage(next)
    persistLanguage(next)
    persistToBackend(theme, next, previewProfiles)
  }

  function setPreviewProfile(profile: PreviewProfileKey, next: PreviewStyleProfile) {
    const nextProfiles = { ...previewProfiles, [profile]: next }
    setPreviewProfilesState(nextProfiles)
    applyPreviewProfiles(nextProfiles)
    window.localStorage.setItem(PREVIEW_PROFILES_STORAGE_KEY, JSON.stringify(nextProfiles))
    persistToBackend(theme, language, nextProfiles)
  }

  return (
    <InterfaceSettingsContext.Provider
      value={{ theme, setTheme, language, setLanguage, previewProfiles, setPreviewProfile }}
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
