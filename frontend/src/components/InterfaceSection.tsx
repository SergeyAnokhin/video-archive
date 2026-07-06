import { useTranslation } from 'react-i18next'
import type { SupportedLanguage } from '../i18n'
import { persistLanguage, SUPPORTED_LANGUAGES } from '../i18n'

export function InterfaceSection() {
  const { t, i18n } = useTranslation()
  const currentLanguage = (i18n.resolvedLanguage ?? 'en') as SupportedLanguage

  function handleLanguageSelect(language: SupportedLanguage) {
    void i18n.changeLanguage(language)
    persistLanguage(language)
  }

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
          {SUPPORTED_LANGUAGES.map((language) => (
            <button
              key={language}
              type="button"
              className="settings-modal__option"
              aria-pressed={currentLanguage === language}
              onClick={() => handleLanguageSelect(language)}
            >
              {t(`language.${language}`)}
            </button>
          ))}
        </div>
      </div>
    </section>
  )
}
