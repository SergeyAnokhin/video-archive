import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from './locales/en.json'
import ru from './locales/ru.json'

export const SUPPORTED_LANGUAGES = ['en', 'ru'] as const
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number]

const STORAGE_KEY = 'video-archive:language'

function detectInitialLanguage(): SupportedLanguage {
  const stored = window.localStorage.getItem(STORAGE_KEY)
  if (stored === 'en' || stored === 'ru') {
    return stored
  }

  const browserLanguage = window.navigator.language?.slice(0, 2).toLowerCase()
  return browserLanguage === 'ru' ? 'ru' : 'en'
}

export function persistLanguage(language: SupportedLanguage) {
  window.localStorage.setItem(STORAGE_KEY, language)
}

void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    ru: { translation: ru },
  },
  lng: detectInitialLanguage(),
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
})

export default i18n
