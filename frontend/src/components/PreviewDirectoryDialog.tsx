import { Play, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import './ConvertDialog.css'

interface PreviewDirectoryDialogProps {
  path: string
  onClose: () => void
  onStarted: () => void
}

export function PreviewDirectoryDialog({ path, onClose, onStarted }: PreviewDirectoryDialogProps) {
  const { t } = useTranslation()
  const [skipProcessed, setSkipProcessed] = useState(true)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleStart() {
    setStarting(true)
    setError(null)
    try {
      const res = await fetch('/api/jobs/preview-directory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, skip_processed: skipProcessed }),
      })
      if (!res.ok) {
        const json = await res.json().catch(() => null)
        throw new Error(json?.detail?.error?.message ?? `HTTP ${res.status}`)
      }
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
        aria-label={t('previewDialog.directoryTitle')}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="convert-dialog__title">{t('previewDialog.directoryTitle')}</h2>
        <p className="convert-dialog__hint">
          {t('convertDialog.scopePath', { path: path || t('library.root') })}
        </p>

        <label className="convert-dialog__checkbox">
          <input
            type="checkbox"
            checked={skipProcessed}
            onChange={(event) => setSkipProcessed(event.target.checked)}
          />
          {t('previewDialog.skipProcessed')}
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
