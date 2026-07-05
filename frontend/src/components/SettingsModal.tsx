import { X } from 'lucide-react'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import type { SupportedLanguage } from '../i18n'
import { persistLanguage, SUPPORTED_LANGUAGES } from '../i18n'
import './SettingsModal.css'

interface SettingsModalProps {
  onClose: () => void
}

export function SettingsModal({ onClose }: SettingsModalProps) {
  const { t, i18n } = useTranslation()
  const currentLanguage = (i18n.resolvedLanguage ?? 'en') as SupportedLanguage

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  function handleLanguageSelect(language: SupportedLanguage) {
    void i18n.changeLanguage(language)
    persistLanguage(language)
  }

  return (
    <div className="settings-modal-overlay" onClick={onClose}>
      <div
        className="settings-modal"
        role="dialog"
        aria-modal="true"
        aria-label={t('settings.title')}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="settings-modal__header">
          <h2 className="settings-modal__title">{t('settings.title')}</h2>
          <button
            type="button"
            className="settings-modal__close"
            aria-label={t('settings.close')}
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </div>

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
      </div>
    </div>
  )
}
