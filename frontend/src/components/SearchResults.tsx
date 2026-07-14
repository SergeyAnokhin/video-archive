import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { FileVideo, Folder, Tag as TagIcon } from 'lucide-react'
import { useInterfaceSettings } from '../context/InterfaceSettingsContext'
import { FileCard, FolderCard } from './LibraryCards'
import type { DirectoryEntry, DirectorySearchResponse, FileEntry } from '../types/api'
import { formatSearchQuery, type ActiveSearch, type SearchScope } from '../utils/searchQuery'
import { sortFiles, type SortBy } from '../utils/sortFiles'
import './LibraryView.css'

// Scoped search results (user request): an unscoped ("all") search renders up
// to three capped sections -- matches found via tags, via file names, and via
// directory names -- each with a button that re-runs the search scoped to
// just that group (`tag:`/`file:`/`path:`). A scoped search renders one flat
// grid that loads more pages as the user scrolls (never the whole source at
// once).
const PAGE_SIZE = 60

interface SearchGroups {
  tagFiles: FileEntry[]
  nameFiles: FileEntry[]
  dirs: DirectoryEntry[]
}

interface SearchResultsProps {
  activeSearch: ActiveSearch
  sortBy: SortBy
  reloadTick: number
  onSearch: (search: ActiveSearch) => void
  onOpenDirectory: (path: string) => void
  onPlayFile: (file: FileEntry) => void
  onInfoFile: (file: FileEntry) => void
  onDeleteFile: (fileId: string) => void
  onToggleFavoriteDirectory: (path: string, favorite: boolean) => void
  onDeleteDirectory: (path: string) => void
}

function fileSearchParams(scope: 'tag' | 'file', term: string): URLSearchParams {
  return new URLSearchParams(scope === 'file' ? { search: term } : { tag_search: term })
}

async function fetchFilePage(params: URLSearchParams, limit: number, offset: number): Promise<FileEntry[]> {
  const page = new URLSearchParams(params)
  page.set('limit', String(limit))
  page.set('offset', String(offset))
  const res = await fetch(`/api/files?${page.toString()}`)
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`)
  }
  const json: { files: FileEntry[] } = await res.json()
  return json.files
}

async function fetchDirPage(term: string, limit: number, offset: number): Promise<DirectoryEntry[]> {
  const params = new URLSearchParams({ q: term, limit: String(limit), offset: String(offset) })
  const res = await fetch(`/api/directories/search?${params.toString()}`)
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`)
  }
  const json: DirectorySearchResponse = await res.json()
  return json.directories
}

export function SearchResults({
  activeSearch,
  sortBy,
  reloadTick,
  onSearch,
  onOpenDirectory,
  onPlayFile,
  onInfoFile,
  onDeleteFile,
  onToggleFavoriteDirectory,
  onDeleteDirectory,
}: SearchResultsProps) {
  const { t } = useTranslation()
  const { searchLimits } = useInterfaceSettings()
  const [groups, setGroups] = useState<SearchGroups | null>(null)
  const [files, setFiles] = useState<FileEntry[] | null>(null)
  const [dirs, setDirs] = useState<DirectoryEntry[] | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const sentinelRef = useRef<HTMLDivElement | null>(null)

  const { scope, value } = activeSearch

  useEffect(() => {
    let cancelled = false
    setGroups(null)
    setFiles(null)
    setDirs(null)
    setHasMore(false)
    setError(null)

    async function load() {
      try {
        if (scope === 'all') {
          const [tagFiles, nameFiles, dirEntries] = await Promise.all([
            fetchFilePage(fileSearchParams('tag', value), searchLimits.tags, 0),
            fetchFilePage(fileSearchParams('file', value), searchLimits.files, 0),
            fetchDirPage(value, searchLimits.dirs, 0),
          ])
          if (!cancelled) {
            setGroups({ tagFiles, nameFiles, dirs: dirEntries })
          }
        } else if (scope === 'path') {
          const page = await fetchDirPage(value, PAGE_SIZE, 0)
          if (!cancelled) {
            setDirs(page)
            setHasMore(page.length === PAGE_SIZE)
          }
        } else {
          const page = await fetchFilePage(fileSearchParams(scope, value), PAGE_SIZE, 0)
          if (!cancelled) {
            setFiles(page)
            setHasMore(page.length === PAGE_SIZE)
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err))
        }
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [scope, value, reloadTick, searchLimits.tags, searchLimits.files, searchLimits.dirs])

  const loadMore = useCallback(async () => {
    if (loadingMore || !hasMore || scope === 'all') {
      return
    }
    setLoadingMore(true)
    try {
      if (scope === 'path') {
        const page = await fetchDirPage(value, PAGE_SIZE, dirs?.length ?? 0)
        setDirs((prev) => [...(prev ?? []), ...page])
        setHasMore(page.length === PAGE_SIZE)
      } else {
        const page = await fetchFilePage(fileSearchParams(scope, value), PAGE_SIZE, files?.length ?? 0)
        setFiles((prev) => [...(prev ?? []), ...page])
        setHasMore(page.length === PAGE_SIZE)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoadingMore(false)
    }
  }, [loadingMore, hasMore, scope, value, dirs?.length, files?.length])

  useEffect(() => {
    const sentinel = sentinelRef.current
    if (!hasMore || !sentinel) {
      return
    }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        void loadMore()
      }
    })
    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [hasMore, loadMore])

  function renderFileGrid(entries: FileEntry[]) {
    return (
      <div className="library-view__grid">
        {sortFiles(entries, sortBy).map((file) => (
          <FileCard
            key={file.id}
            file={file}
            onPlay={() => onPlayFile(file)}
            onInfo={() => onInfoFile(file)}
            onDelete={() => onDeleteFile(file.id)}
          />
        ))}
      </div>
    )
  }

  function renderDirGrid(entries: DirectoryEntry[]) {
    return (
      <div className="library-view__grid">
        {entries.map((dir) => (
          <FolderCard
            key={dir.path}
            dir={dir}
            onOpen={() => onOpenDirectory(dir.path)}
            onToggleFavorite={() => onToggleFavoriteDirectory(dir.path, !dir.is_favorite)}
            onDelete={() => onDeleteDirectory(dir.path)}
          />
        ))}
      </div>
    )
  }

  function groupSection(
    icon: ReactNode,
    labelKey: string,
    narrowScope: Exclude<SearchScope, 'all'>,
    content: ReactNode,
  ) {
    return (
      <section className="library-view__search-group">
        <div className="library-view__search-group-header">
          {icon}
          <h3>{t(labelKey)}</h3>
          <button
            type="button"
            className="library-view__search-narrow"
            title={t('library.searchNarrow')}
            onClick={() => onSearch({ scope: narrowScope, label: formatSearchQuery(narrowScope, value), value })}
          >
            {formatSearchQuery(narrowScope, value)}
          </button>
        </div>
        {content}
      </section>
    )
  }

  if (error) {
    return (
      <p className="library-view__message library-view__message--error">
        {t('library.loadError', { message: error })}
      </p>
    )
  }

  if (scope === 'all') {
    if (!groups) {
      return <p className="library-view__message">{t('library.loading')}</p>
    }
    const empty = groups.tagFiles.length === 0 && groups.nameFiles.length === 0 && groups.dirs.length === 0
    if (empty) {
      return <p className="library-view__message">{t('library.searchEmpty')}</p>
    }
    return (
      <>
        {groups.tagFiles.length > 0 &&
          groupSection(<TagIcon size={14} />, 'library.searchGroupTags', 'tag', renderFileGrid(groups.tagFiles))}
        {groups.nameFiles.length > 0 &&
          groupSection(
            <FileVideo size={14} />,
            'library.searchGroupFiles',
            'file',
            renderFileGrid(groups.nameFiles),
          )}
        {groups.dirs.length > 0 &&
          groupSection(<Folder size={14} />, 'library.searchGroupDirs', 'path', renderDirGrid(groups.dirs))}
      </>
    )
  }

  const items = scope === 'path' ? dirs : files
  if (!items) {
    return <p className="library-view__message">{t('library.loading')}</p>
  }
  if (items.length === 0) {
    return <p className="library-view__message">{t('library.searchEmpty')}</p>
  }
  return (
    <>
      {scope === 'path' ? renderDirGrid(dirs ?? []) : renderFileGrid(files ?? [])}
      {hasMore && (
        <div ref={sentinelRef} className="library-view__search-sentinel">
          {t('library.searchLoadingMore')}
        </div>
      )}
    </>
  )
}
