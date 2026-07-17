import { Play, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import './ConvertDialog.css'

interface TagDirectoryDialogProps {
  path: string
  onClose: () => void
  onStarted: () => void
}

export function TagDirectoryDialog({ path, onClose, onStarted }: TagDirectoryDialogProps) {
  const { t } = useTranslation()
  const [skipProcessed, setSkipProcessed] = useState(true)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleStart() {
    setStarting(true)
    setError(null)
    try {
      await api('/api/jobs/tag-directory', {
        method: 'POST',
        body: { path, skip_processed: skipProcessed },
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
        aria-label={t('tagDialog.directoryTitle')}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="convert-dialog__title">{t('tagDialog.directoryTitle')}</h2>
        <p className="convert-dialog__hint">
          {t('convertDialog.scopePath', { path: path || t('library.root') })}
        </p>

        <label className="convert-dialog__checkbox">
          <input
            type="checkbox"
            checked={skipProcessed}
            onChange={(event) => setSkipProcessed(event.target.checked)}
          />
          {t('tagDialog.skipProcessed')}
        </label>

        {error && <p className="convert-dialog__hint convert-dialog__hint--error">{error}</p>}

        <div className="convert-dialog__actions">
          <button
            type="button"
            className="convert-dialog__button convert-dialog__button--primary"
            onClick={handleStart}
            disabled={starting}
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
