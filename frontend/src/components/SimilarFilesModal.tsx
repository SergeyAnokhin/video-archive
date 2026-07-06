import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { FileEntry, SimilarFile } from '../types/api'
import './ConvertDialog.css'
import './SimilarFilesModal.css'

interface SimilarFilesModalProps {
  file: FileEntry
  onClose: () => void
}

export function SimilarFilesModal({ file, onClose }: SimilarFilesModalProps) {
  const { t } = useTranslation()
  const [results, setResults] = useState<SimilarFile[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const res = await fetch(`/api/files/${file.id}/similar`)
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`)
        }
        const json: { similar: SimilarFile[] } = await res.json()
        if (!cancelled) {
          setResults(json.similar)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err))
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [file.id])

  return (
    <div className="convert-dialog-overlay" onClick={onClose}>
      <div
        className="convert-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={t('library.similarTitle', { name: file.file_name })}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="convert-dialog__title">{t('library.similarTitle', { name: file.file_name })}</h2>

        {error && (
          <p className="convert-dialog__hint convert-dialog__hint--error">
            {t('playbackModal.loadError', { message: error })}
          </p>
        )}
        {!error && !results && <p className="convert-dialog__hint">{t('library.loading')}</p>}
        {results && results.length === 0 && <p className="convert-dialog__hint">{t('library.similarEmpty')}</p>}

        {results && results.length > 0 && (
          <ul className="similar-files-modal__list">
            {results.map((entry) => (
              <li key={entry.file_id} className="similar-files-modal__item">
                <span className="similar-files-modal__path">{entry.relative_path}</span>
                <span className="similar-files-modal__distance">
                  {t('library.similarDistance', { distance: entry.distance })}
                </span>
              </li>
            ))}
          </ul>
        )}

        <div className="convert-dialog__actions">
          <button type="button" className="convert-dialog__button" onClick={onClose}>
            {t('library.similarClose')}
          </button>
        </div>
      </div>
    </div>
  )
}
