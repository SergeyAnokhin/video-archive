import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Folder, History } from 'lucide-react'
import { api, tryApi } from '../api/client'
import type { DirectoryEntry, FavoriteDirectory } from '../types/api'
import { getRecentFolders, recordFolderVisit } from '../utils/recentFolders'
import { DirectoryMoveMenu } from './DirectoryMoveMenu'
import { HistoryFolderMenu } from './HistoryFolderMenu'
import './FolderQuickActions.css'

interface FolderQuickActionsProps {
  fileId: string
  onMoved: () => void
}

// Shared button row mounted top-left in both PlaybackModal and
// FileInfoPanel: a "History" button (recently viewed-from folders, leftmost)
// plus one button per favorite folder, all moving the current file there.
export function FolderQuickActions({ fileId, onMoved }: FolderQuickActionsProps) {
  const { t } = useTranslation()
  const [favorites, setFavorites] = useState<FavoriteDirectory[]>([])
  const [openMenu, setOpenMenu] = useState<string | null>(null) // a favorite's path, 'history', or null
  const [checkingPath, setCheckingPath] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const history = getRecentFolders()

  useEffect(() => {
    let cancelled = false
    tryApi<{ favorites: FavoriteDirectory[] }>('/api/directories/favorites')
      .then((json) => {
        if (!cancelled) {
          setFavorites(json?.favorites ?? [])
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!openMenu) {
      return
    }
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpenMenu(null)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [openMenu])

  async function moveTo(path: string) {
    setError(null)
    try {
      await api(`/api/files/${fileId}/move`, {
        method: 'POST',
        body: { target_directory: path },
      })
      recordFolderVisit(path)
      setOpenMenu(null)
      onMoved()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleFavoriteClick(fav: FavoriteDirectory) {
    if (openMenu === fav.path) {
      setOpenMenu(null)
      return
    }
    setCheckingPath(fav.path)
    setError(null)
    try {
      const json = await tryApi<{ directories: DirectoryEntry[] }>(
        `/api/directories/children?path=${encodeURIComponent(fav.path)}`,
      )
      if ((json?.directories ?? []).length === 0) {
        await moveTo(fav.path)
      } else {
        setOpenMenu(fav.path)
      }
    } finally {
      setCheckingPath(null)
    }
  }

  if (favorites.length === 0 && history.length === 0) {
    return null
  }

  return (
    <div className="folder-quick-actions" ref={containerRef}>
      {history.length > 0 && (
        <div className="folder-quick-actions__item">
          <button
            type="button"
            className="folder-quick-actions__button"
            aria-label={t('library.folderHistory')}
            title={t('library.folderHistory')}
            onClick={() => setOpenMenu(openMenu === 'history' ? null : 'history')}
          >
            <History size={14} />
          </button>
          {openMenu === 'history' && (
            <div className="folder-quick-actions__history-menu" onClick={(event) => event.stopPropagation()}>
              <HistoryFolderMenu paths={history} rootLabel={t('library.root')} onSelect={(path) => void moveTo(path)} />
            </div>
          )}
        </div>
      )}

      {favorites.map((fav) => (
        <div className="folder-quick-actions__item" key={fav.path}>
          <button
            type="button"
            className="folder-quick-actions__button"
            title={fav.path || t('library.root')}
            onClick={() => void handleFavoriteClick(fav)}
            disabled={checkingPath === fav.path}
          >
            <Folder size={14} /> {fav.name}
          </button>
          {openMenu === fav.path && (
            <DirectoryMoveMenu rootPath={fav.path} rootName={fav.name} onPick={(path) => void moveTo(path)} />
          )}
        </div>
      ))}

      {error && <div className="folder-quick-actions__error">{error}</div>}
    </div>
  )
}
