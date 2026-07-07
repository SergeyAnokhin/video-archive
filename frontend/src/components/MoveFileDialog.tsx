import { ChevronRight, Folder, FolderInput, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { DirectoryEntry, FileEntry } from '../types/api'
import './ConvertDialog.css'
import './MoveFileDialog.css'

interface MoveFileDialogProps {
  file: FileEntry
  currentPath: string
  onClose: () => void
  onMoved: () => void
}

export function MoveFileDialog({ file, currentPath, onClose, onMoved }: MoveFileDialogProps) {
  const { t } = useTranslation()
  const [selected, setSelected] = useState(currentPath)
  const [moving, setMoving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleMove() {
    setMoving(true)
    setError(null)
    try {
      const res = await fetch(`/api/files/${file.id}/move`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_directory: selected }),
      })
      if (!res.ok) {
        const json = await res.json().catch(() => null)
        const code = json?.detail?.error?.code
        if (code === 'same_location') {
          throw new Error(t('library.moveFileSameLocation'))
        }
        if (code === 'destination_collision') {
          throw new Error(t('library.moveFileCollision'))
        }
        throw new Error(json?.detail?.error?.message ?? `HTTP ${res.status}`)
      }
      onMoved()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setMoving(false)
    }
  }

  return (
    <div className="convert-dialog-overlay" onClick={onClose}>
      <div
        className="convert-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={t('library.moveFileTitle', { name: file.file_name })}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="convert-dialog__title">{t('library.moveFileTitle', { name: file.file_name })}</h2>
        <p className="convert-dialog__hint">{t('library.moveFileHint')}</p>

        <div className="move-file-dialog__tree">
          <DirectoryTreeNode path="" name={t('library.root')} depth={0} selected={selected} onSelect={setSelected} />
        </div>

        <p className="convert-dialog__hint">
          {t('library.moveFileSelected', { path: selected || t('library.root') })}
        </p>

        {error && <p className="convert-dialog__hint convert-dialog__hint--error">{error}</p>}

        <div className="convert-dialog__actions">
          <button
            type="button"
            className="convert-dialog__button convert-dialog__button--primary"
            onClick={handleMove}
            disabled={moving || selected === currentPath}
          >
            <FolderInput size={14} /> {t('library.moveFileConfirm')}
          </button>
          <button type="button" className="convert-dialog__button" onClick={onClose}>
            <X size={14} /> {t('convertDialog.cancel')}
          </button>
        </div>
      </div>
    </div>
  )
}

interface DirectoryTreeNodeProps {
  path: string
  name: string
  depth: number
  selected: string
  onSelect: (path: string) => void
}

function DirectoryTreeNode({ path, name, depth, selected, onSelect }: DirectoryTreeNodeProps) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(depth === 0)
  const [children, setChildren] = useState<DirectoryEntry[] | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!expanded || children !== null) {
      return
    }
    let cancelled = false
    setLoading(true)
    fetch(`/api/directories/children?path=${encodeURIComponent(path)}`)
      .then((res) => (res.ok ? res.json() : { directories: [] }))
      .then((json: { directories: DirectoryEntry[] }) => {
        if (!cancelled) {
          setChildren(json.directories)
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [expanded, children, path])

  return (
    <div className="move-file-dialog__node">
      <div className="move-file-dialog__row" style={{ paddingLeft: depth * 16 }}>
        <button
          type="button"
          className="move-file-dialog__expand"
          onClick={() => setExpanded((value) => !value)}
          aria-label={t(expanded ? 'library.collapseFolder' : 'library.expandFolder')}
        >
          <ChevronRight size={14} className={expanded ? 'move-file-dialog__expand-icon--open' : undefined} />
        </button>
        <button
          type="button"
          className={`move-file-dialog__label ${selected === path ? 'move-file-dialog__label--selected' : ''}`}
          onClick={() => onSelect(path)}
        >
          <Folder size={14} /> {name}
        </button>
      </div>
      {expanded && (
        <div className="move-file-dialog__children">
          {loading && <p className="move-file-dialog__loading">…</p>}
          {children?.map((dir) => (
            <DirectoryTreeNode
              key={dir.path}
              path={dir.path}
              name={dir.name}
              depth={depth + 1}
              selected={selected}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  )
}
