import { Trash2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import './ConvertDialog.css'

interface OrphanedPreviewsDialogProps {
  path: string
  onClose: () => void
  onDeleted: () => void
}

interface DryRunResult {
  count: number
  sample: string[]
}

export function OrphanedPreviewsDialog({ path, onClose, onDeleted }: OrphanedPreviewsDialogProps) {
  const { t } = useTranslation()
  const [result, setResult] = useState<DryRunResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    void (async () => {
      try {
        const query = new URLSearchParams({ path }).toString()
        const data = await api<DryRunResult>(`/api/directories/orphaned-previews?${query}`)
        if (!cancelled) setResult(data)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [path])

  async function handleDelete() {
    setDeleting(true)
    setError(null)
    try {
      await api('/api/directories/orphaned-previews/delete', {
        method: 'POST',
        body: { path },
      })
      onDeleted()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="convert-dialog-overlay" onClick={onClose}>
      <div
        className="convert-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={t('orphanedPreviewsDialog.title')}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="convert-dialog__title">{t('orphanedPreviewsDialog.title')}</h2>
        <p className="convert-dialog__hint">
          {t('orphanedPreviewsDialog.scopePath', { path: path || t('library.root') })}
        </p>

        {loading && <p className="convert-dialog__hint">{t('orphanedPreviewsDialog.checking')}</p>}

        {!loading && result && (
          <>
            {result.count === 0 ? (
              <p className="convert-dialog__hint">{t('orphanedPreviewsDialog.empty')}</p>
            ) : (
              <>
                <p className="convert-dialog__hint">
                  {t('orphanedPreviewsDialog.count', { count: result.count })}
                </p>
                <ul className="orphaned-previews-dialog__list">
                  {result.sample.map((name) => (
                    <li key={name}>{name}</li>
                  ))}
                </ul>
                {result.count > result.sample.length && (
                  <p className="convert-dialog__hint">
                    {t('orphanedPreviewsDialog.andMore', { count: result.count - result.sample.length })}
                  </p>
                )}
              </>
            )}
          </>
        )}

        {error && <p className="convert-dialog__hint convert-dialog__hint--error">{error}</p>}

        <div className="convert-dialog__actions">
          <button
            type="button"
            className="convert-dialog__button convert-dialog__button--primary"
            onClick={handleDelete}
            disabled={loading || deleting || !result || result.count === 0}
          >
            <Trash2 size={14} /> {t('orphanedPreviewsDialog.run')}
          </button>
          <button type="button" className="convert-dialog__button" onClick={onClose}>
            <X size={14} /> {t('convertDialog.cancel')}
          </button>
        </div>
      </div>
    </div>
  )
}
