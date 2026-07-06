import { X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { SupportedLanguage } from '../i18n'
import { persistLanguage, SUPPORTED_LANGUAGES } from '../i18n'
import { useConversionProfiles } from '../context/ConversionProfilesContext'
import { useSource } from '../context/SourceContext'
import type { ConversionProfile, SourceConfig, TestConnectionResult } from '../types/api'
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

        <ConversionProfilesSection />

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

type ProfileFormValue = ConversionProfile | 'new' | null

function ConversionProfilesSection() {
  const { t } = useTranslation()
  const { profiles, refresh } = useConversionProfiles()
  const [editing, setEditing] = useState<ProfileFormValue>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  async function handleDelete(id: string) {
    setBusyId(id)
    try {
      await fetch(`/api/conversion-profiles/${id}`, { method: 'DELETE' })
      await refresh()
    } finally {
      setBusyId(null)
    }
  }

  async function handleSetDefault(profile: ConversionProfile) {
    setBusyId(profile.id)
    try {
      await fetch(`/api/conversion-profiles/${profile.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...profile, is_default: true }),
      })
      await refresh()
    } finally {
      setBusyId(null)
    }
  }

  function handleDuplicate(profile: ConversionProfile) {
    setEditing({
      ...profile,
      id: '',
      name: t('conversionProfiles.duplicateName', { name: profile.name }),
      is_default: false,
    })
  }

  return (
    <section className="settings-modal__section">
      <h3 className="settings-modal__section-title">{t('conversionProfiles.title')}</h3>

      {profiles.length === 0 && (
        <p className="settings-modal__hint">{t('conversionProfiles.empty')}</p>
      )}

      {profiles.map((profile) => (
        <div key={profile.id} className="conversion-profile-row">
          <div>
            <span className="settings-modal__field-label">{profile.name}</span>
            {profile.is_default && (
              <span className="conversion-profile-row__badge">{t('conversionProfiles.default')}</span>
            )}
            <p className="settings-modal__hint">
              {t('conversionProfiles.summary', {
                codec: profile.video_codec.toUpperCase(),
                crf: profile.crf,
                dimension: profile.max_dimension
                  ? `${profile.max_dimension}px`
                  : t('conversionProfiles.noResize'),
              })}
            </p>
          </div>
          <div className="settings-modal__actions">
            {!profile.is_default && (
              <button
                type="button"
                className="settings-modal__option"
                onClick={() => handleSetDefault(profile)}
                disabled={busyId === profile.id}
              >
                {t('conversionProfiles.markDefault')}
              </button>
            )}
            <button type="button" className="settings-modal__option" onClick={() => setEditing(profile)}>
              {t('conversionProfiles.edit')}
            </button>
            <button
              type="button"
              className="settings-modal__option"
              onClick={() => handleDuplicate(profile)}
            >
              {t('conversionProfiles.duplicate')}
            </button>
            <button
              type="button"
              className="settings-modal__option"
              onClick={() => handleDelete(profile.id)}
              disabled={busyId === profile.id}
            >
              {t('conversionProfiles.delete')}
            </button>
          </div>
        </div>
      ))}

      {editing === null ? (
        <div className="settings-modal__actions">
          <button type="button" className="settings-modal__option" onClick={() => setEditing('new')}>
            {t('conversionProfiles.add')}
          </button>
        </div>
      ) : (
        <ConversionProfileForm
          initial={editing === 'new' ? null : editing}
          onCancel={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null)
            await refresh()
          }}
        />
      )}
    </section>
  )
}

interface ConversionProfileFormProps {
  initial: ConversionProfile | null
  onCancel: () => void
  onSaved: () => Promise<void>
}

function ConversionProfileForm({ initial, onCancel, onSaved }: ConversionProfileFormProps) {
  const { t } = useTranslation()
  const [name, setName] = useState(initial?.name ?? '')
  const [videoCodec, setVideoCodec] = useState(initial?.video_codec ?? 'h265')
  const [maxDimension, setMaxDimension] = useState(initial?.max_dimension?.toString() ?? '')
  const [crf, setCrf] = useState(initial?.crf?.toString() ?? '26')
  const [dropAudio, setDropAudio] = useState(initial?.drop_audio ?? true)
  const [isDefault, setIsDefault] = useState(initial?.is_default ?? false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSave() {
    setSaving(true)
    setError(null)
    try {
      const body = {
        name,
        video_codec: videoCodec,
        container: 'mp4',
        max_dimension: maxDimension ? Number(maxDimension) : null,
        crf: Number(crf),
        drop_audio: dropAudio,
        is_default: isDefault,
      }
      const editingExisting = Boolean(initial && initial.id)
      const url = editingExisting
        ? `/api/conversion-profiles/${initial!.id}`
        : '/api/conversion-profiles'
      const res = await fetch(url, {
        method: editingExisting ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const json = await res.json().catch(() => null)
        throw new Error(json?.detail?.error?.message ?? `HTTP ${res.status}`)
      }
      await onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="conversion-profile-form">
      <label className="settings-modal__label">
        {t('conversionProfiles.name')}
        <input
          className="settings-modal__input"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>

      <label className="settings-modal__label">
        {t('conversionProfiles.codec')}
        <select
          className="settings-modal__input"
          value={videoCodec}
          onChange={(event) => setVideoCodec(event.target.value)}
        >
          <option value="h265">H.265</option>
          <option value="h264">H.264</option>
          <option value="vp9">VP9</option>
          <option value="av1">AV1</option>
        </select>
      </label>

      <label className="settings-modal__label">
        {t('conversionProfiles.maxDimension')}
        <input
          className="settings-modal__input"
          type="number"
          min={1}
          value={maxDimension}
          onChange={(event) => setMaxDimension(event.target.value)}
          placeholder={t('conversionProfiles.noResize')}
        />
      </label>

      <label className="settings-modal__label">
        {t('conversionProfiles.crf')}
        <input
          className="settings-modal__input"
          type="number"
          min={22}
          max={32}
          value={crf}
          onChange={(event) => setCrf(event.target.value)}
        />
      </label>

      <label className="settings-modal__field">
        <span className="settings-modal__field-label">{t('conversionProfiles.dropAudio')}</span>
        <input
          type="checkbox"
          checked={dropAudio}
          onChange={(event) => setDropAudio(event.target.checked)}
        />
      </label>

      <label className="settings-modal__field">
        <span className="settings-modal__field-label">{t('conversionProfiles.markDefault')}</span>
        <input
          type="checkbox"
          checked={isDefault}
          onChange={(event) => setIsDefault(event.target.checked)}
        />
      </label>

      {error && <p className="settings-modal__hint settings-modal__hint--error">{error}</p>}

      <div className="settings-modal__actions">
        <button
          type="button"
          className="settings-modal__option"
          onClick={handleSave}
          disabled={saving || !name}
        >
          {t('conversionProfiles.save')}
        </button>
        <button type="button" className="settings-modal__option" onClick={onCancel}>
          {t('settings.cancel')}
        </button>
      </div>
    </div>
  )
}
