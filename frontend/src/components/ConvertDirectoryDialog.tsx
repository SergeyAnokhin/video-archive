import { Play, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useConversionProfiles } from '../context/ConversionProfilesContext'
import { api } from '../api/client'
import type { ConversionMode } from '../types/api'
import './ConvertDialog.css'

interface ConvertDirectoryDialogProps {
  path: string
  onClose: () => void
  onStarted: () => void
}

export function ConvertDirectoryDialog({ path, onClose, onStarted }: ConvertDirectoryDialogProps) {
  const { t } = useTranslation()
  const { profiles } = useConversionProfiles()
  const [profileId, setProfileId] = useState(profiles.find((p) => p.is_default)?.id ?? profiles[0]?.id ?? '')
  const [mode, setMode] = useState<ConversionMode>('production')
  const [skipProcessed, setSkipProcessed] = useState(true)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleStart() {
    setStarting(true)
    setError(null)
    try {
      await api('/api/jobs/convert-directory', {
        method: 'POST',
        body: { path, profile_id: profileId, mode, skip_processed: skipProcessed },
      })
      onStarted()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setStarting(false)
    }
  }

  return (
    <div className="convert-dialog-overlay" onClick={onClose}>
      <div
        className="convert-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={t('convertDialog.directoryTitle')}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="convert-dialog__title">{t('convertDialog.directoryTitle')}</h2>
        <p className="convert-dialog__hint">
          {t('convertDialog.scopePath', { path: path || t('library.root') })}
        </p>

        {profiles.length === 0 ? (
          <p className="convert-dialog__hint convert-dialog__hint--warning">
            {t('convertDialog.noProfiles')}
          </p>
        ) : (
          <>
            <label className="convert-dialog__label">
              {t('convertDialog.profile')}
              <select
                className="convert-dialog__input"
                value={profileId}
                onChange={(event) => setProfileId(event.target.value)}
              >
                {profiles.map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {profile.name}
                  </option>
                ))}
              </select>
            </label>

            <fieldset className="convert-dialog__fieldset">
              <legend>{t('convertDialog.mode')}</legend>
              <label className="convert-dialog__radio">
                <input
                  type="radio"
                  checked={mode === 'production'}
                  onChange={() => setMode('production')}
                />
                {t('convertDialog.modeProduction')}
              </label>
              <label className="convert-dialog__radio">
                <input type="radio" checked={mode === 'test'} onChange={() => setMode('test')} />
                {t('convertDialog.modeTest')}
              </label>
            </fieldset>

            <label className="convert-dialog__checkbox">
              <input
                type="checkbox"
                checked={skipProcessed}
                onChange={(event) => setSkipProcessed(event.target.checked)}
              />
              {t('convertDialog.skipProcessed')}
            </label>
          </>
        )}

        {error && <p className="convert-dialog__hint convert-dialog__hint--error">{error}</p>}

        <div className="convert-dialog__actions">
          <button
            type="button"
            className="convert-dialog__button convert-dialog__button--primary"
            onClick={handleStart}
            disabled={starting || !profileId}
          >
            <Play size={14} /> {t('convertDialog.start')}
          </button>
          <button type="button" className="convert-dialog__button" onClick={onClose}>
            <X size={14} /> {t('convertDialog.cancel')}
          </button>
        </div>
      </div>
    </div>
  )
}
