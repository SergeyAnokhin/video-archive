import { Copy, Pencil, Plus, Save, Star, Trash2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useConversionProfiles } from '../context/ConversionProfilesContext'
import { api, tryApi } from '../api/client'
import { useBackendStatus } from '../hooks/useBackendStatus'
import type { ConversionProfile, ConversionSettings } from '../types/api'

type ProfileFormValue = ConversionProfile | 'new' | null

type ConversionSettingsField = 'min_size_reduction_percent' | 'ffmpeg_timeout_seconds'

function ConversionSettingsFields() {
  const { t } = useTranslation()
  const [settings, setSettings] = useState<ConversionSettings | null>(null)

  useEffect(() => {
    void (async () => {
      const loaded = await tryApi<ConversionSettings>('/api/conversion-settings')
      if (loaded) {
        setSettings(loaded)
      }
    })()
  }, [])

  // All fields always ship together in one PUT (same gotcha as
  // BackendHealthSettingsSection) -- sending just the changed one would let
  // the backend's per-field `Field(default=...)` silently reset the others
  // back to their default on an omitted key.
  async function save(next: ConversionSettings) {
    setSettings(next)
    const saved = await tryApi<ConversionSettings>('/api/conversion-settings', {
      method: 'PUT',
      body: {
        min_size_reduction_percent: next.min_size_reduction_percent,
        ffmpeg_timeout_seconds: next.ffmpeg_timeout_seconds,
        direct_write_enabled: next.direct_write_enabled,
      },
    })
    if (saved) setSettings(saved)
  }

  async function handleChange(field: ConversionSettingsField, value: number) {
    if (!settings) return
    await save({ ...settings, [field]: value })
  }

  async function handleDirectWriteChange(value: boolean) {
    if (!settings) return
    await save({ ...settings, direct_write_enabled: value })
  }

  if (!settings) return null

  return (
    <>
      <label className="settings-modal__label">
        {t('conversionProfiles.minSizeReduction')}
        <input
          className="settings-modal__input"
          type="number"
          min={0}
          max={90}
          value={settings.min_size_reduction_percent}
          onChange={(event) => void handleChange('min_size_reduction_percent', Number(event.target.value))}
        />
        <span className="settings-modal__hint">{t('conversionProfiles.minSizeReductionHint')}</span>
      </label>
      <label className="settings-modal__label">
        {t('conversionProfiles.ffmpegTimeout')}
        <input
          className="settings-modal__input"
          type="number"
          min={60}
          max={86400}
          value={settings.ffmpeg_timeout_seconds}
          onChange={(event) => void handleChange('ffmpeg_timeout_seconds', Number(event.target.value))}
        />
        <span className="settings-modal__hint">{t('conversionProfiles.ffmpegTimeoutHint')}</span>
      </label>
      <label className="settings-modal__field">
        <span className="settings-modal__field-label">{t('conversionProfiles.directWrite')}</span>
        <input
          type="checkbox"
          checked={settings.direct_write_enabled}
          onChange={(event) => void handleDirectWriteChange(event.target.checked)}
        />
      </label>
      <p className="settings-modal__hint">{t('conversionProfiles.directWriteHint')}</p>
    </>
  )
}

export function ConversionProfilesSection() {
  const { t } = useTranslation()
  const { profiles, refresh } = useConversionProfiles()
  const [editing, setEditing] = useState<ProfileFormValue>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  async function handleDelete(id: string) {
    setBusyId(id)
    try {
      await tryApi(`/api/conversion-profiles/${id}`, { method: 'DELETE' })
      await refresh()
    } finally {
      setBusyId(null)
    }
  }

  async function handleSetDefault(profile: ConversionProfile) {
    setBusyId(profile.id)
    try {
      await tryApi(`/api/conversion-profiles/${profile.id}`, {
        method: 'PUT',
        body: { ...profile, is_default: true },
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

      <ConversionSettingsFields />

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
                className="settings-modal__option settings-modal__option--icon"
                onClick={() => handleSetDefault(profile)}
                disabled={busyId === profile.id}
                aria-label={t('conversionProfiles.markDefault')}
                title={t('conversionProfiles.markDefault')}
              >
                <Star size={14} />
              </button>
            )}
            <button
              type="button"
              className="settings-modal__option settings-modal__option--icon"
              onClick={() => setEditing(profile)}
              aria-label={t('conversionProfiles.edit')}
              title={t('conversionProfiles.edit')}
            >
              <Pencil size={14} />
            </button>
            <button
              type="button"
              className="settings-modal__option settings-modal__option--icon"
              onClick={() => handleDuplicate(profile)}
              aria-label={t('conversionProfiles.duplicate')}
              title={t('conversionProfiles.duplicate')}
            >
              <Copy size={14} />
            </button>
            <button
              type="button"
              className="settings-modal__option settings-modal__option--icon"
              onClick={() => handleDelete(profile.id)}
              disabled={busyId === profile.id}
              aria-label={t('conversionProfiles.delete')}
              title={t('conversionProfiles.delete')}
            >
              <Trash2 size={14} />
            </button>
          </div>
        </div>
      ))}

      {editing === null ? (
        <div className="settings-modal__actions">
          <button type="button" className="settings-modal__option" onClick={() => setEditing('new')}>
            <Plus size={14} /> {t('conversionProfiles.add')}
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
  const [hardwareAccel, setHardwareAccel] = useState(initial?.hardware_accel ?? 'off')
  const [isDefault, setIsDefault] = useState(initial?.is_default ?? false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const backendStatus = useBackendStatus()
  const hardwareAccelInfo = backendStatus.phase === 'ready' ? backendStatus.appInfo.hardware_accel : null

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
        hardware_accel: hardwareAccel,
        is_default: isDefault,
      }
      const editingExisting = Boolean(initial && initial.id)
      const url = editingExisting
        ? `/api/conversion-profiles/${initial!.id}`
        : '/api/conversion-profiles'
      await api(url, {
        method: editingExisting ? 'PUT' : 'POST',
        body,
      })
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
        {t('conversionProfiles.hardwareAccel')}
        <select
          className="settings-modal__input"
          value={hardwareAccel}
          onChange={(event) => setHardwareAccel(event.target.value)}
        >
          <option value="off">{t('conversionProfiles.hardwareAccelOff')}</option>
          <option value="qsv">
            {t('conversionProfiles.hardwareAccelQsv')}
            {hardwareAccelInfo && !hardwareAccelInfo.qsv ? ` (${t('conversionProfiles.hardwareAccelUnavailable')})` : ''}
          </option>
          <option value="vaapi">
            {t('conversionProfiles.hardwareAccelVaapi')}
            {hardwareAccelInfo && !hardwareAccelInfo.vaapi ? ` (${t('conversionProfiles.hardwareAccelUnavailable')})` : ''}
          </option>
        </select>
        <span className="settings-modal__hint">{t('conversionProfiles.hardwareAccelHint')}</span>
      </label>

      <div className="settings-modal__row">
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
      </div>

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
          <Save size={14} /> {t('conversionProfiles.save')}
        </button>
        <button type="button" className="settings-modal__option" onClick={onCancel}>
          <X size={14} /> {t('settings.cancel')}
        </button>
      </div>
    </div>
  )
}
