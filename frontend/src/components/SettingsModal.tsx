import { X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { SupportedLanguage } from '../i18n'
import { persistLanguage, SUPPORTED_LANGUAGES } from '../i18n'
import { useSource } from '../context/SourceContext'
import type { SourceConfig, TestConnectionResult } from '../types/api'
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

        <SourceSection />

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

function SourceSection() {
  const { t } = useTranslation()
  const { source, loading: sourceLoading, setSource } = useSource()
  const [name, setName] = useState('')
  const [rootPath, setRootPath] = useState('')
  const [testResult, setTestResult] = useState<TestConnectionResult | null>(null)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [confirmingReplace, setConfirmingReplace] = useState(false)

  useEffect(() => {
    if (source) {
      setName(source.name)
      setRootPath(source.root_path)
    }
  }, [source])

  async function handleTestConnection() {
    setTesting(true)
    setTestResult(null)
    try {
      const res = await fetch('/api/source/test-connection', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, protocol: 'local', root_path: rootPath }),
      })
      const json: TestConnectionResult = await res.json()
      setTestResult(json)
    } catch (err) {
      setTestResult({ ok: false, message: err instanceof Error ? err.message : String(err) })
    } finally {
      setTesting(false)
    }
  }

  async function handleSave() {
    if (source && !confirmingReplace) {
      setConfirmingReplace(true)
      return
    }

    setSaving(true)
    setSaveError(null)
    try {
      const res = await fetch('/api/source', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, protocol: 'local', root_path: rootPath }),
      })
      if (!res.ok) {
        const json = await res.json().catch(() => null)
        throw new Error(json?.error?.message ?? `HTTP ${res.status}`)
      }
      const json: SourceConfig = await res.json()
      setSource(json)
      setConfirmingReplace(false)
      setTestResult(null)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="settings-modal__section">
      <h3 className="settings-modal__section-title">{t('settings.sourceSection')}</h3>

      {source && (
        <p className="settings-modal__hint">
          {t('settings.currentSource', { name: source.name, path: source.root_path })}
          {' '}
          {source.last_scan_at
            ? t('settings.lastScan', { date: new Date(source.last_scan_at).toLocaleString() })
            : t('settings.neverScanned')}
        </p>
      )}
      {!sourceLoading && !source && (
        <p className="settings-modal__hint">{t('settings.noSourceYet')}</p>
      )}

      <label className="settings-modal__label">
        {t('settings.sourceName')}
        <input
          className="settings-modal__input"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>

      <label className="settings-modal__label">
        {t('settings.sourcePath')}
        <input
          className="settings-modal__input"
          value={rootPath}
          onChange={(event) => setRootPath(event.target.value)}
          placeholder="./library"
        />
      </label>

      <p className="settings-modal__hint">{t('settings.sourceProtocolLocal')}</p>

      {testResult && (
        <p
          className={`settings-modal__hint${testResult.ok ? '' : ' settings-modal__hint--error'}`}
        >
          {testResult.ok
            ? t('settings.testOk')
            : t('settings.testFail', { message: testResult.message })}
        </p>
      )}
      {saveError && (
        <p className="settings-modal__hint settings-modal__hint--error">{saveError}</p>
      )}
      {confirmingReplace && (
        <p className="settings-modal__hint settings-modal__hint--warning">
          {t('settings.replaceWarning')}
        </p>
      )}

      <div className="settings-modal__actions">
        <button
          type="button"
          className="settings-modal__option"
          onClick={handleTestConnection}
          disabled={testing || !rootPath}
        >
          {t('settings.testConnection')}
        </button>
        <button
          type="button"
          className="settings-modal__option"
          onClick={handleSave}
          disabled={saving || !name || !rootPath}
        >
          {confirmingReplace ? t('settings.confirmReplace') : t('settings.saveSource')}
        </button>
        {confirmingReplace && (
          <button
            type="button"
            className="settings-modal__option"
            onClick={() => setConfirmingReplace(false)}
          >
            {t('settings.cancel')}
          </button>
        )}
      </div>
    </section>
  )
}
