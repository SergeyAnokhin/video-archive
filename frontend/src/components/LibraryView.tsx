import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowDownAZ, HardDrive, Home, Images, MoreVertical, RefreshCw, Tag, Tags, Wand2, X } from 'lucide-react'
import { useJobs } from '../context/JobsContext'
import { ConvertDirectoryDialog } from './ConvertDirectoryDialog'
import { FileConvertModal } from './FileConvertModal'
import { FileInfoPanel } from './FileInfoPanel'
import { FileTuneModal } from './FileTuneModal'
import { FileCard, FolderCard } from './LibraryCards'
import type { ActiveSearch } from './LibrarySearchBox'
import { MoveFileDialog } from './MoveFileDialog'
import { PlaybackModal } from './PlaybackModal'
import { PreviewDirectoryDialog } from './PreviewDirectoryDialog'
import { SimilarFilesModal } from './SimilarFilesModal'
import { TagDirectoryDialog } from './TagDirectoryDialog'
import type { DirectoryChildrenResponse, FileEntry, JobSummary, VariantTag } from '../types/api'
import { recordRecentlyViewed } from '../utils/recentlyViewed'
import './LibraryView.css'

interface LibraryViewProps {
  path: string
  onNavigate: (path: string) => void
  activeSearch: ActiveSearch | null
  onClearSearch: () => void
}

type SortBy = 'name' | 'size' | 'tags'

const SORT_OPTIONS: SortBy[] = ['name', 'size', 'tags']

// Mirrors the top-bar theme cycle button (TopBar.tsx): a single icon button
// that steps through a small fixed set of options on click, rather than a
// dropdown -- avoids sitting a dropdown right next to the job-creating icon
// buttons (convert/preview/tag).
const SORT_ICON: Record<SortBy, typeof ArrowDownAZ> = {
  name: ArrowDownAZ,
  size: HardDrive,
  tags: Tag,
}

const SORT_LABEL_KEY: Record<SortBy, string> = {
  name: 'library.sortByName',
  size: 'library.sortBySize',
  tags: 'library.sortByTags',
}

function variantTagSortKey(tag: VariantTag): string {
  const value = typeof tag.value === 'number' ? tag.value.toString().padStart(8, '0') : tag.value
  return `${tag.param}:${value}`
}

function compareByTags(a: FileEntry, b: FileEntry): number {
  const aKeys = (a.variant_tags ?? []).map(variantTagSortKey).sort()
  const bKeys = (b.variant_tags ?? []).map(variantTagSortKey).sort()
  const length = Math.max(aKeys.length, bKeys.length)
  for (let i = 0; i < length; i++) {
    if (aKeys[i] === undefined) return bKeys[i] === undefined ? 0 : -1
    if (bKeys[i] === undefined) return 1
    if (aKeys[i] !== bKeys[i]) return aKeys[i] < bKeys[i] ? -1 : 1
  }
  return 0
}

function sortFiles(files: FileEntry[], sortBy: SortBy): FileEntry[] {
  const sorted = [...files]
  switch (sortBy) {
    case 'name':
      sorted.sort((a, b) => a.file_name.localeCompare(b.file_name))
      break
    case 'size':
      sorted.sort((a, b) => a.size_bytes - b.size_bytes)
      break
    case 'tags':
      sorted.sort(compareByTags)
      break
  }
  return sorted
}

export function LibraryView({ path, onNavigate, activeSearch, onClearSearch }: LibraryViewProps) {
  const { t } = useTranslation()
  const { activeJob, refresh: refreshJobs } = useJobs()
  const [data, setData] = useState<DirectoryChildrenResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [rescanning, setRescanning] = useState(false)
  const [convertDirOpen, setConvertDirOpen] = useState(false)
  const [convertFile, setConvertFile] = useState<FileEntry | null>(null)
  const [tuneFile, setTuneFile] = useState<FileEntry | null>(null)
  const [previewDirOpen, setPreviewDirOpen] = useState(false)
  const [previewingFileId, setPreviewingFileId] = useState<string | null>(null)
  const [tagDirOpen, setTagDirOpen] = useState(false)
  const [taggingFileId, setTaggingFileId] = useState<string | null>(null)
  const [playingFile, setPlayingFile] = useState<FileEntry | null>(null)
  const [similarFile, setSimilarFile] = useState<FileEntry | null>(null)
  const [infoFile, setInfoFile] = useState<FileEntry | null>(null)
  const [moveFile, setMoveFile] = useState<FileEntry | null>(null)
  const [searchResults, setSearchResults] = useState<FileEntry[] | null>(null)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [overflowOpen, setOverflowOpen] = useState(false)
  const [sortBy, setSortBy] = useState<SortBy>('name')
  const [reloadTick, setReloadTick] = useState(0)
  const overflowRef = useRef<HTMLDivElement | null>(null)
  const prevActiveJobRef = useRef<JobSummary | null>(null)

  // A finished job (preview/tag/convert) may have changed this directory's
  // files, but nothing else refetches on job completion -- do it here so a
  // newly generated thumbnail/status shows up without a manual reload.
  useEffect(() => {
    if (prevActiveJobRef.current && !activeJob) {
      setReloadTick((tick) => tick + 1)
    }
    prevActiveJobRef.current = activeJob
  }, [activeJob])

  useEffect(() => {
    if (!overflowOpen) {
      return
    }
    function handleClickOutside(event: MouseEvent) {
      if (overflowRef.current && !overflowRef.current.contains(event.target as Node)) {
        setOverflowOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [overflowOpen])

  useEffect(() => {
    if (!activeSearch) {
      return
    }
    let cancelled = false
    setSearchResults(null)
    setSearchError(null)

    async function loadSearch() {
      try {
        const params = new URLSearchParams(
          activeSearch!.kind === 'tag' ? { tags: activeSearch!.value } : { search: activeSearch!.value },
        )
        const res = await fetch(`/api/files?${params.toString()}`)
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`)
        }
        const json: { files: FileEntry[] } = await res.json()
        if (!cancelled) {
          setSearchResults(json.files)
        }
      } catch (err) {
        if (!cancelled) {
          setSearchError(err instanceof Error ? err.message : String(err))
        }
      }
    }

    void loadSearch()
    return () => {
      cancelled = true
    }
  }, [activeSearch])

  useEffect(() => {
    if (activeSearch) {
      return
    }
    let cancelled = false
    setData(null)
    setError(null)

    async function load() {
      try {
        const params = new URLSearchParams({ path, include_status: 'true' })
        const res = await fetch(`/api/directories/children?${params.toString()}`)
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`)
        }
        const json: DirectoryChildrenResponse = await res.json()
        if (!cancelled) {
          setData(json)
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
  }, [path, activeSearch, reloadTick])

  const segments = path ? path.split('/') : []

  const nextSortBy = SORT_OPTIONS[(SORT_OPTIONS.indexOf(sortBy) + 1) % SORT_OPTIONS.length]
  const SortIcon = SORT_ICON[sortBy]
  const sortToggleLabel = t('library.sortToggle', { mode: t(SORT_LABEL_KEY[nextSortBy]) })

  const directoryActions = [
    { key: 'convert', label: t('library.convert'), icon: <Wand2 size={16} />, onClick: () => setConvertDirOpen(true) },
    { key: 'preview', label: t('library.preview'), icon: <Images size={16} />, onClick: () => setPreviewDirOpen(true) },
    { key: 'tag', label: t('library.tag'), icon: <Tags size={16} />, onClick: () => setTagDirOpen(true) },
  ]

  async function handleRescan() {
    setRescanning(true)
    try {
      await fetch('/api/jobs/rescan-directory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      })
      await refreshJobs()
    } finally {
      setRescanning(false)
    }
  }

  async function handlePreviewFile(fileId: string) {
    setPreviewingFileId(fileId)
    try {
      await fetch('/api/jobs/preview-file', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_id: fileId }),
      })
      await refreshJobs()
    } finally {
      setPreviewingFileId(null)
    }
  }

  async function handleTagFile(fileId: string) {
    setTaggingFileId(fileId)
    try {
      await fetch('/api/jobs/tag-file', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_id: fileId }),
      })
      await refreshJobs()
    } finally {
      setTaggingFileId(null)
    }
  }

  async function handleDeleteFile(fileId: string) {
    const res = await fetch(`/api/files/${fileId}`, { method: 'DELETE' })
    if (res.ok) {
      setInfoFile(null)
      setReloadTick((tick) => tick + 1)
    }
  }

  return (
    <div className="library-view">
      <div className="library-view__toolbar">
        <nav className="library-view__breadcrumb" aria-label={t('library.breadcrumb')}>
          <button type="button" onClick={() => onNavigate('')}>
            <Home size={14} /> {t('library.root')}
          </button>
          {segments.map((segment, index) => {
            const segmentPath = segments.slice(0, index + 1).join('/')
            return (
              <span key={segmentPath}>
                <span className="library-view__breadcrumb-sep">/</span>
                <button type="button" onClick={() => onNavigate(segmentPath)}>
                  {segment}
                </button>
              </span>
            )
          })}
        </nav>

        <div className="library-view__toolbar-actions">
          <button
            type="button"
            className="library-view__icon-btn"
            aria-label={sortToggleLabel}
            title={sortToggleLabel}
            onClick={() => setSortBy(nextSortBy)}
          >
            <SortIcon size={16} />
          </button>

          <span className="library-view__toolbar-divider" aria-hidden="true" />

          <button
            type="button"
            className="library-view__icon-btn"
            aria-label={t('library.rescan')}
            title={t('library.rescan')}
            onClick={handleRescan}
            disabled={rescanning}
          >
            <RefreshCw size={16} className={rescanning ? 'library-view__icon-spin' : undefined} />
          </button>

          {/* Design System §5 (< 640px): secondary icon buttons collapse into an
              overflow menu; the same actions render inline on tablet/desktop. */}
          {directoryActions.map((action) => (
            <button
              key={action.key}
              type="button"
              className="library-view__icon-btn library-view__actions-inline"
              aria-label={action.label}
              title={action.label}
              onClick={action.onClick}
            >
              {action.icon}
            </button>
          ))}

          <div className="library-view__overflow" ref={overflowRef}>
            <button
              type="button"
              className="library-view__icon-btn library-view__overflow-trigger"
              aria-label={t('library.moreActions')}
              aria-haspopup="menu"
              aria-expanded={overflowOpen}
              onClick={() => setOverflowOpen((open) => !open)}
            >
              <MoreVertical size={16} />
            </button>
            {overflowOpen && (
              <div className="library-view__overflow-menu" role="menu">
                {directoryActions.map((action) => (
                  <button
                    key={action.key}
                    type="button"
                    role="menuitem"
                    className="library-view__overflow-item"
                    onClick={() => {
                      action.onClick()
                      setOverflowOpen(false)
                    }}
                  >
                    {action.icon}
                    <span>{action.label}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {activeSearch && (
        <div className="library-view__search-banner">
          <span>{t('library.searchResultsFor', { query: activeSearch.label })}</span>
          <button type="button" className="library-view__icon-btn" onClick={onClearSearch}>
            <X size={14} />
          </button>
        </div>
      )}

      {activeSearch ? (
        <>
          {searchError && (
            <p className="library-view__message library-view__message--error">
              {t('library.loadError', { message: searchError })}
            </p>
          )}
          {!searchError && !searchResults && <p className="library-view__message">{t('library.loading')}</p>}
          {searchResults && searchResults.length === 0 && (
            <p className="library-view__message">{t('library.searchEmpty')}</p>
          )}
          {searchResults && searchResults.length > 0 && (
            <div className="library-view__grid">
              {sortFiles(searchResults, sortBy).map((file) => (
                <FileCard
                  key={file.id}
                  file={file}
                  onPlay={() => {
                    recordRecentlyViewed(file.id)
                    setPlayingFile(file)
                  }}
                  onInfo={() => setInfoFile(file)}
                  onDelete={() => void handleDeleteFile(file.id)}
                />
              ))}
            </div>
          )}
        </>
      ) : (
        <>
          {error && (
            <p className="library-view__message library-view__message--error">
              {t('library.loadError', { message: error })}
            </p>
          )}

          {!error && !data && <p className="library-view__message">{t('library.loading')}</p>}

          {data && data.directories.length === 0 && data.files.length === 0 && (
            <p className="library-view__message">{t('library.empty')}</p>
          )}

          {data && (data.directories.length > 0 || data.files.length > 0) && (
            <div className="library-view__grid">
              {data.directories.map((dir) => (
                <FolderCard key={dir.path} dir={dir} onOpen={() => onNavigate(dir.path)} />
              ))}
              {sortFiles(data.files, sortBy).map((file) => (
                <FileCard
                  key={file.id}
                  file={file}
                  onPlay={() => {
                    recordRecentlyViewed(file.id)
                    setPlayingFile(file)
                  }}
                  onInfo={() => setInfoFile(file)}
                  onDelete={() => void handleDeleteFile(file.id)}
                />
              ))}
            </div>
          )}
        </>
      )}

      {convertDirOpen && (
        <ConvertDirectoryDialog
          path={path}
          onClose={() => setConvertDirOpen(false)}
          onStarted={refreshJobs}
        />
      )}

      {convertFile && (
        <FileConvertModal
          file={convertFile}
          onClose={() => setConvertFile(null)}
          onStarted={refreshJobs}
        />
      )}

      {tuneFile && (
        <FileTuneModal
          file={tuneFile}
          onClose={() => setTuneFile(null)}
          onStarted={refreshJobs}
        />
      )}

      {previewDirOpen && (
        <PreviewDirectoryDialog
          path={path}
          onClose={() => setPreviewDirOpen(false)}
          onStarted={refreshJobs}
        />
      )}

      {tagDirOpen && (
        <TagDirectoryDialog
          path={path}
          onClose={() => setTagDirOpen(false)}
          onStarted={refreshJobs}
        />
      )}

      {playingFile && <PlaybackModal file={playingFile} onClose={() => setPlayingFile(null)} />}
      {similarFile && <SimilarFilesModal file={similarFile} onClose={() => setSimilarFile(null)} />}
      {infoFile && (
        <FileInfoPanel
          file={infoFile}
          previewing={previewingFileId === infoFile.id}
          tagging={taggingFileId === infoFile.id}
          onClose={() => setInfoFile(null)}
          onPreview={() => void handlePreviewFile(infoFile.id)}
          onTag={() => void handleTagFile(infoFile.id)}
          onConvert={() => {
            setConvertFile(infoFile)
            setInfoFile(null)
          }}
          onTune={() => {
            setTuneFile(infoFile)
            setInfoFile(null)
          }}
          onSimilar={() => {
            setSimilarFile(infoFile)
            setInfoFile(null)
          }}
          onDelete={() => void handleDeleteFile(infoFile.id)}
          onMove={() => {
            setMoveFile(infoFile)
            setInfoFile(null)
          }}
        />
      )}

      {moveFile && (
        <MoveFileDialog
          file={moveFile}
          currentPath={path}
          onClose={() => setMoveFile(null)}
          onMoved={() => {
            setMoveFile(null)
            setReloadTick((tick) => tick + 1)
          }}
        />
      )}
    </div>
  )
}

