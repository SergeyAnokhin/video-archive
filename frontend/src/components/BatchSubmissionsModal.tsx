import { X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { BatchSubmission } from '../types/api'
import './ConvertDialog.css'
import './BatchSubmissionsModal.css'

interface BatchSubmissionsModalProps {
  onClose: () => void
}

const REFRESH_INTERVAL_MS = 5000

export function BatchSubmissionsModal({ onClose }: BatchSubmissionsModalProps) {
  const { t } = useTranslation()
  const [submissions, setSubmissions] = useState<BatchSubmission[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  async function refresh() {
    try {
      const res = await fetch('/api/jobs/batch-submissions')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json: { submissions: BatchSubmission[] } = await res.json()
      setSubmissions(json.submissions)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => void refresh(), REFRESH_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [])

  async function handleForget(id: string) {
    if (!window.confirm(t('batchSubmissions.confirmForget'))) return
    setBusyId(id)
    try {
      await fetch(`/api/jobs/batch-submissions/${id}`, { method: 'DELETE' })
      await refresh()
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="convert-dialog-overlay" onClick={onClose}>
      <div
        className="convert-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={t('batchSubmissions.title')}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="convert-dialog__title">{t('batchSubmissions.title')}</h2>
        <p className="convert-dialog__hint">{t('batchSubmissions.hint')}</p>

        {error && (
          <p className="convert-dialog__hint convert-dialog__hint--error">
            {t('playbackModal.loadError', { message: error })}
          </p>
        )}
        {!error && submissions === null && <p className="convert-dialog__hint">{t('library.loading')}</p>}
        {submissions && submissions.length === 0 && (
          <p className="convert-dialog__hint">{t('batchSubmissions.empty')}</p>
        )}

        {submissions && submissions.length > 0 && (
          <ul className="batch-submissions-modal__list">
            {submissions.map((submission) => (
              <li key={submission.id} className="batch-submissions-modal__item">
                <span className="batch-submissions-modal__label">
                  {t(`providers.${submission.provider_type}`)} / {submission.model_name ?? t('providerUsage.notAvailable')}
                  {' — '}
                  {t('batchSubmissions.itemCount', { count: submission.item_count })}
                  {' — '}
                  {new Date(submission.created_at).toLocaleString()}
                </span>
                <button
                  type="button"
                  className="convert-dialog__button"
                  onClick={() => void handleForget(submission.id)}
                  disabled={busyId === submission.id}
                >
                  {t('batchSubmissions.forget')}
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="convert-dialog__actions">
          <button type="button" className="convert-dialog__button" onClick={onClose}>
            <X size={14} /> {t('library.similarClose')}
          </button>
        </div>
      </div>
    </div>
  )
}
