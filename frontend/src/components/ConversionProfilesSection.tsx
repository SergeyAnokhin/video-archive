import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useConversionProfiles } from '../context/ConversionProfilesContext'
import type { ConversionProfile } from '../types/api'

type ProfileFormValue = ConversionProfile | 'new' | null

export function ConversionProfilesSection() {
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
