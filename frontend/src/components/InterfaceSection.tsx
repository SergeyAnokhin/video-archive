import { useTranslation } from 'react-i18next'
import { SUPPORTED_LANGUAGES } from '../i18n'
import { useInterfaceSettings } from '../context/InterfaceSettingsContext'
import type { ThemePreset } from '../types/api'

const THEME_PRESETS: ThemePreset[] = ['strict', 'playful']

export function InterfaceSection() {
  const { t } = useTranslation()
  const { language, setLanguage, theme, setTheme } = useInterfaceSettings()

  return (
    <section className="settings-modal__section">
      <h3 className="settings-modal__section-title">
        {t('settings.interfaceSection')}
      </h3>
      <div className="settings-modal__field">
        <span className="settings-modal__field-label">
          {t('settings.language')}
        </span>
        <div
          className="settings-modal__options"
          role="group"
          aria-label={t('settings.language')}
        >
          {SUPPORTED_LANGUAGES.map((option) => (
            <button
              key={option}
              type="button"
              className="settings-modal__option"
              aria-pressed={language === option}
              onClick={() => setLanguage(option)}
            >
              {t(`language.${option}`)}
            </button>
          ))}
        </div>
      </div>
      <div className="settings-modal__field">
        <span className="settings-modal__field-label">
          {t('settings.theme')}
        </span>
        <div
          className="settings-modal__options"
          role="group"
          aria-label={t('settings.theme')}
        >
          {THEME_PRESETS.map((option) => (
            <button
              key={option}
              type="button"
              className="settings-modal__option"
              aria-pressed={theme === option}
              onClick={() => setTheme(option)}
            >
              {t(`theme.${option}`)}
            </button>
          ))}
        </div>
      </div>
    </section>
  )
}
