import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, Check, ChevronRight, Folder } from 'lucide-react'
import { tryApi } from '../api/client'
import type { DirectoryEntry } from '../types/api'
import './DirectoryMoveMenu.css'

interface DirectoryMoveMenuProps {
  rootPath: string
  rootName: string
  onPick: (path: string) => void
}

// Compact anchored flyout for picking a move destination under a favorite
// folder or a history entry: "move here" for the level currently shown, plus
// lazily-loaded subfolders to drill into (back button to go up). Deliberately
// separate from MoveFileDialog's always-expanded tree -- that dialog starts
// browsing from the source root, this one starts (and stays) rooted at a
// single folder and shows one level at a time in a small popover.
export function DirectoryMoveMenu({ rootPath, rootName, onPick }: DirectoryMoveMenuProps) {
  const { t } = useTranslation()
  const [stack, setStack] = useState<{ path: string; name: string }[]>([{ path: rootPath, name: rootName }])
  const [children, setChildren] = useState<DirectoryEntry[] | null>(null)
  const [loading, setLoading] = useState(false)

  const current = stack[stack.length - 1]

  useEffect(() => {
    let cancelled = false
    setChildren(null)
    setLoading(true)
    tryApi<{ directories: DirectoryEntry[] }>(`/api/directories/children?path=${encodeURIComponent(current.path)}`)
      .then((json) => {
        if (!cancelled) {
          setChildren(json?.directories ?? [])
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
  }, [current.path])

  return (
    <div className="directory-move-menu" onClick={(event) => event.stopPropagation()}>
      <div className="directory-move-menu__header">
        {stack.length > 1 && (
          <button
            type="button"
            className="directory-move-menu__back"
            aria-label={t('library.moveMenuBack')}
            onClick={() => setStack((s) => s.slice(0, -1))}
          >
            <ArrowLeft size={14} />
          </button>
        )}
        <span className="directory-move-menu__title" title={current.name}>
          {current.name}
        </span>
      </div>

      <button type="button" className="directory-move-menu__here" onClick={() => onPick(current.path)}>
        <Check size={14} /> {t('library.moveMenuHere')}
      </button>

      {loading && <p className="directory-move-menu__loading">{t('library.loading')}</p>}

      {children && children.length > 0 && (
        <div className="directory-move-menu__children">
          {children.map((dir) => (
            <button
              key={dir.path}
              type="button"
              className="directory-move-menu__child"
              onClick={() => setStack((s) => [...s, { path: dir.path, name: dir.name }])}
            >
              <Folder size={14} />
              <span>{dir.name}</span>
              <ChevronRight size={14} className="directory-move-menu__child-chevron" />
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
