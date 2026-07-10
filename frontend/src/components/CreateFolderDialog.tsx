import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { FolderPlus, X } from 'lucide-react'
import './ConvertDialog.css'

interface CreateFolderDialogProps {
  parentPath: string
  onClose: () => void
  onCreated: () => void
}

export function CreateFolderDialog({ parentPath, onClose, onCreated }: CreateFolderDialogProps) {
  const { t } = useTranslation()
  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleCreate() {
    setCreating(true)
    setError(null)
    try {
      const res = await fetch('/api/directories', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ parent_path: parentPath, name }),
      })
      if (!res.ok) {
        const json = await res.json().catch(() => null)
        const code = json?.detail?.error?.code
        if (code === 'invalid_name') {
          throw new Error(t('library.createFolderInvalidName'))
        }
        if (code === 'destination_collision') {
          throw new Error(t('library.createFolderCollision'))
        }
        throw new Error(json?.detail?.error?.message ?? `HTTP ${res.status}`)
      }
      onCreated()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="convert-dialog-overlay" onClick={onClose}>
      <div
        className="convert-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={t('library.createFolderTitle')}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="convert-dialog__title">{t('library.createFolderTitle')}</h2>

        <label className="convert-dialog__label">
          {t('library.createFolderNameLabel')}
          <input
            type="text"
            className="convert-dialog__input"
            value={name}
            autoFocus
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && name.trim() && !creating) {
                void handleCreate()
              }
            }}
          />
        </label>

        {error && <p className="convert-dialog__hint convert-dialog__hint--error">{error}</p>}

        <div className="convert-dialog__actions">
          <button
            type="button"
            className="convert-dialog__button convert-dialog__button--primary"
            onClick={() => void handleCreate()}
            disabled={creating || !name.trim()}
          >
            <FolderPlus size={14} /> {t('library.createFolderConfirm')}
          </button>
          <button type="button" className="convert-dialog__button" onClick={onClose}>
            <X size={14} /> {t('convertDialog.cancel')}
          </button>
        </div>
      </div>
    </div>
  )
}
