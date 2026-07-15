import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  ArrowDownAZ,
  FolderPlus,
  HardDrive,
  History,
  Home,
  Images,
  MoreVertical,
  RefreshCw,
  Tag,
  Tags,
  Wand2,
  X,
} from 'lucide-react'
import { useJobs } from '../context/JobsContext'
import { ConvertDirectoryDialog } from './ConvertDirectoryDialog'
import { CreateFolderDialog } from './CreateFolderDialog'
import { FileConvertModal } from './FileConvertModal'
import { FileInfoPanel } from './FileInfoPanel'
import { FileTuneModal } from './FileTuneModal'
import { HistoryFolderMenu } from './HistoryFolderMenu'
import { ImageViewerModal } from './ImageViewerModal'
import { FileCard, FolderCard } from './LibraryCards'
import { MoveFileDialog } from './MoveFileDialog'
import { PlaybackModal } from './PlaybackModal'
import { PreviewDirectoryDialog } from './PreviewDirectoryDialog'
import { SearchResults } from './SearchResults'
import { SimilarFilesModal } from './SimilarFilesModal'
import { TagDirectoryDialog } from './TagDirectoryDialog'
import { TagLabModal } from './TagLabModal'
import type { DirectoryChildrenResponse, FileEntry, JobSummary } from '../types/api'
import { getRecentFolderVisits, recordFolderVisit, recordRecentFolder } from '../utils/recentFolders'
import { recordRecentlyViewed } from '../utils/recentlyViewed'
import type { ActiveSearch } from '../utils/searchQuery'
import { SORT_OPTIONS, sortFiles, type SortBy } from '../utils/sortFiles'
import './LibraryView.css'

interface LibraryViewProps {
  path: string
  onNavigate: (path: string) => void
  activeSearch: ActiveSearch | null
  onSearch: (search: ActiveSearch) => void
  onClearSearch: () => void
}

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

export function LibraryView({ path, onNavigate, activeSearch, onSearch, onClearSearch }: LibraryViewProps) {
  const { t } = useTranslation()
  const { activeJob, jobItemsById, refresh: refreshJobs } = useJobs()
  const [data, setData] = useState<DirectoryChildrenResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [rescanning, setRescanning] = useState(false)
  const [convertDirOpen, setConvertDirOpen] = useState(false)
  const [convertFile, setConvertFile] = useState<FileEntry | null>(null)
  const [tuneFile, setTuneFile] = useState<FileEntry | null>(null)
  const [previewDirOpen, setPreviewDirOpen] = useState(false)
  const [previewingFileId, setPreviewingFileId] = useState<string | null>(null)
  const [tagDirOpen, setTagDirOpen] = useState(false)
  const [tagLabFile, setTagLabFile] = useState<FileEntry | null>(null)
  const [playingFile, setPlayingFile] = useState<FileEntry | null>(null)
  const [similarFile, setSimilarFile] = useState<FileEntry | null>(null)
  const [infoFile, setInfoFile] = useState<FileEntry | null>(null)
  const [moveFile, setMoveFile] = useState<FileEntry | null>(null)
  const [overflowOpen, setOverflowOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [sortBy, setSortBy] = useState<SortBy>('name')
  const [reloadTick, setReloadTick] = useState(0)
  const [createFolderOpen, setCreateFolderOpen] = useState(false)
  const overflowRef = useRef<HTMLDivElement | null>(null)
  const historyRef = useRef<HTMLDivElement | null>(null)
  const prevActiveJobRef = useRef<JobSummary | null>(null)
  // Tags edited inside FileInfoPanel must show on the cards as soon as the
  // panel closes (user request) -- the panel reports each successful tag
  // mutation here, and the pending flag turns into one refetch on close.
  const infoTagsChangedRef = useRef(false)
  // Same batching for tags added via the playback screen's quick tag-add
  // control (user request) -- see closePlayback()/openInfoFromPlayback().
  const playingTagsChangedRef = useRef(false)
  // Per-file job items already completed and folded into this directory's
  // data, so a still-running job's later poll ticks don't re-trigger the
  // same reload (user request: preview/tag/convert results should appear as
  // each file finishes, not only once the whole job is done).
  const appliedCompletedItemIdsRef = useRef<Set<string>>(new Set())
  // Tracks which folder path the grid was last loaded for, so a same-folder
  // silent reload can be told apart from an actual navigation (see the data
  // effect below).
  const lastLoadedPathRef = useRef<string | null>(null)

  // A finished job (preview/tag/convert) may have changed this directory's
  // files, but nothing else refetches on job completion -- do it here so a
  // newly generated thumbnail/status shows up without a manual reload.
  useEffect(() => {
    if (prevActiveJobRef.current && !activeJob) {
      setReloadTick((tick) => tick + 1)
    }
    prevActiveJobRef.current = activeJob
  }, [activeJob])

  // Live per-item updates: as soon as an individual file's job item finishes
  // (rather than waiting for the whole job to finish), reload this directory
  // so its new preview/tags/conversion result shows up immediately.
  useEffect(() => {
    if (activeSearch || !data) {
      return
    }
    const currentFileIds = new Set(data.files.map((file) => file.id))
    const newlyCompleted = Object.values(jobItemsById)
      .flat()
      .filter(
        (item) =>
          item.status === 'completed' &&
          item.file_id &&
          currentFileIds.has(item.file_id) &&
          !appliedCompletedItemIdsRef.current.has(item.id),
      )
    if (newlyCompleted.length === 0) {
      return
    }
    for (const item of newlyCompleted) {
      appliedCompletedItemIdsRef.current.add(item.id)
    }
    setReloadTick((tick) => tick + 1)
  }, [jobItemsById, data, activeSearch])

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
    if (!historyOpen) {
      return
    }
    function handleClickOutside(event: MouseEvent) {
      if (historyRef.current && !historyRef.current.contains(event.target as Node)) {
        setHistoryOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [historyOpen])

  useEffect(() => {
    if (activeSearch) {
      return
    }
    let cancelled = false
    // Only show the loading state when actually navigating to a different
    // folder -- a same-folder reload (job completion, move/delete, live
    // per-item update) fetches quietly and swaps the grid's data in place,
    // so cards update without a flash back to "Loading..." (user request).
    const isNewLocation = lastLoadedPathRef.current !== path
    lastLoadedPathRef.current = path
    if (isNewLocation) {
      setData(null)
      setError(null)
    }

    async function load() {
      try {
        const params = new URLSearchParams({ path, include_status: 'true', include_top_tags: 'true' })
        const res = await fetch(`/api/directories/children?${params.toString()}`)
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`)
        }
        const json: DirectoryChildrenResponse = await res.json()
        if (!cancelled) {
          setData(json)
          setError(null)
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
  const recentVisits = getRecentFolderVisits().filter((visitPath) => visitPath !== path)

  // Next/prev navigation in PlaybackModal/FileInfoPanel only makes sense
  // against this directory's own sorted listing (user request) -- search
  // results keep their separate inline sortFiles() call below and don't
  // participate in next/prev.
  const sortedFiles = data ? sortFiles(data.files, sortBy) : []
  const playingIndex = playingFile ? sortedFiles.findIndex((f) => f.id === playingFile.id) : -1
  const infoIndex = infoFile ? sortedFiles.findIndex((f) => f.id === infoFile.id) : -1

  function handleMoved() {
    setPlayingFile(null)
    setInfoFile(null)
    setReloadTick((tick) => tick + 1)
  }

  function goToPlayingOffset(offset: number) {
    const target = sortedFiles[playingIndex + offset]
    if (target) {
      if (target.is_video_supported) {
        recordRecentlyViewed(target.id)
      }
      setPlayingFile(target)
    }
  }

  function goToInfoOffset(offset: number) {
    const target = sortedFiles[infoIndex + offset]
    if (target) {
      setInfoFile(target)
    }
  }

  function closePlayback() {
    setPlayingFile(null)
    if (playingTagsChangedRef.current) {
      playingTagsChangedRef.current = false
      setReloadTick((tick) => tick + 1)
    }
  }

  // Playback screen's quick tag-add button (user request) switches straight
  // into the info panel for the same file instead of stacking a second
  // overlay -- any tag added while still on the playback screen carries
  // forward into the info panel's own batched refresh-on-close.
  function openInfoFromPlayback() {
    if (playingTagsChangedRef.current) {
      playingTagsChangedRef.current = false
      infoTagsChangedRef.current = true
    }
    setInfoFile(playingFile)
    setPlayingFile(null)
  }

  function closeInfoPanel() {
    setInfoFile(null)
    if (infoTagsChangedRef.current) {
      infoTagsChangedRef.current = false
      setReloadTick((tick) => tick + 1)
    }
  }

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

  async function handleDeleteFile(fileId: string) {
    const res = await fetch(`/api/files/${fileId}`, { method: 'DELETE' })
    if (res.ok) {
      setInfoFile(null)
      setReloadTick((tick) => tick + 1)
    }
  }

  async function handleToggleFavoriteFolder(dirPath: string, favorite: boolean) {
    const res = await fetch('/api/directories/favorite', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: dirPath, favorite }),
    })
    if (res.ok) {
      setReloadTick((tick) => tick + 1)
    }
  }

  async function handleDeleteFolder(dirPath: string) {
    const res = await fetch(`/api/directories?${new URLSearchParams({ path: dirPath }).toString()}`, {
      method: 'DELETE',
    })
    if (res.ok) {
      setReloadTick((tick) => tick + 1)
    } else {
      const json = await res.json().catch(() => null)
      const code = json?.detail?.error?.code
      window.alert(code === 'directory_not_empty' ? t('library.deleteFolderNotEmpty') : t('library.deleteFolderFailed'))
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
          <div className="library-view__history" ref={historyRef}>
            <button
              type="button"
              className="library-view__icon-btn"
              aria-label={t('library.folderNavHistory')}
              title={t('library.folderNavHistory')}
              aria-haspopup="menu"
              aria-expanded={historyOpen}
              disabled={recentVisits.length === 0}
              onClick={() => setHistoryOpen((open) => !open)}
            >
              <History size={16} />
            </button>
            {historyOpen && recentVisits.length > 0 && (
              <div className="library-view__history-menu">
                <HistoryFolderMenu
                  paths={recentVisits}
                  rootLabel={t('library.root')}
                  onSelect={(path) => {
                    onNavigate(path)
                    setHistoryOpen(false)
                  }}
                />
              </div>
            )}
          </div>

          <span className="library-view__toolbar-divider" aria-hidden="true" />

          <button
            type="button"
            className="library-view__icon-btn"
            aria-label={t('library.createFolder')}
            title={t('library.createFolder')}
            onClick={() => setCreateFolderOpen(true)}
          >
            <FolderPlus size={16} />
          </button>

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
        <SearchResults
          activeSearch={activeSearch}
          sortBy={sortBy}
          reloadTick={reloadTick}
          onSearch={onSearch}
          onOpenDirectory={(dirPath) => {
            onClearSearch()
            onNavigate(dirPath)
          }}
          onPlayFile={(file) => {
            if (file.is_video_supported) {
              recordRecentlyViewed(file.id)
            }
            setPlayingFile(file)
          }}
          onInfoFile={setInfoFile}
          onDeleteFile={(fileId) => void handleDeleteFile(fileId)}
          onToggleFavoriteDirectory={(dirPath, favorite) => void handleToggleFavoriteFolder(dirPath, favorite)}
          onDeleteDirectory={(dirPath) => void handleDeleteFolder(dirPath)}
        />
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
                <FolderCard
                  key={dir.path}
                  dir={dir}
                  onOpen={() => onNavigate(dir.path)}
                  onToggleFavorite={() => void handleToggleFavoriteFolder(dir.path, !dir.is_favorite)}
                  onDelete={() => void handleDeleteFolder(dir.path)}
                />
              ))}
              {sortedFiles.map((file) => (
                <FileCard
                  key={file.id}
                  file={file}
                  onPlay={() => {
                    if (file.is_video_supported) {
                      recordRecentlyViewed(file.id)
                    }
                    recordRecentFolder(path)
                    recordFolderVisit(path)
                    setPlayingFile(file)
                  }}
                  onInfo={() => {
                    recordRecentFolder(path)
                    setInfoFile(file)
                  }}
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

      {playingFile && playingFile.is_video_supported && (
        <PlaybackModal
          file={playingFile}
          onClose={closePlayback}
          onMoved={handleMoved}
          onOpenInfo={openInfoFromPlayback}
          onTagAdded={() => {
            playingTagsChangedRef.current = true
          }}
          hasPrev={playingIndex > 0}
          hasNext={playingIndex >= 0 && playingIndex < sortedFiles.length - 1}
          onPrev={() => goToPlayingOffset(-1)}
          onNext={() => goToPlayingOffset(1)}
        />
      )}
      {playingFile && !playingFile.is_video_supported && (
        <ImageViewerModal
          file={playingFile}
          onClose={closePlayback}
          onMoved={handleMoved}
          onOpenInfo={openInfoFromPlayback}
          onTagAdded={() => {
            playingTagsChangedRef.current = true
          }}
          hasPrev={playingIndex > 0}
          hasNext={playingIndex >= 0 && playingIndex < sortedFiles.length - 1}
          onPrev={() => goToPlayingOffset(-1)}
          onNext={() => goToPlayingOffset(1)}
        />
      )}
      {similarFile && <SimilarFilesModal file={similarFile} onClose={() => setSimilarFile(null)} />}
      {tagLabFile && (
        <TagLabModal
          file={tagLabFile}
          onClose={() => setTagLabFile(null)}
          onApplied={() => {
            setTagLabFile(null)
            setReloadTick((tick) => tick + 1)
          }}
        />
      )}
      {infoFile && (
        <FileInfoPanel
          file={infoFile}
          previewing={previewingFileId === infoFile.id}
          onClose={closeInfoPanel}
          onPreview={() => void handlePreviewFile(infoFile.id)}
          onTag={() => {
            setTagLabFile(infoFile)
            closeInfoPanel()
          }}
          onConvert={() => {
            setConvertFile(infoFile)
            closeInfoPanel()
          }}
          onTune={() => {
            setTuneFile(infoFile)
            closeInfoPanel()
          }}
          onSimilar={() => {
            setSimilarFile(infoFile)
            closeInfoPanel()
          }}
          onDelete={() => void handleDeleteFile(infoFile.id)}
          onMove={() => {
            setMoveFile(infoFile)
            closeInfoPanel()
          }}
          onMoved={handleMoved}
          onTagsChanged={() => {
            infoTagsChangedRef.current = true
          }}
          hasPrev={infoIndex > 0}
          hasNext={infoIndex >= 0 && infoIndex < sortedFiles.length - 1}
          onPrev={() => goToInfoOffset(-1)}
          onNext={() => goToInfoOffset(1)}
        />
      )}

      {createFolderOpen && (
        <CreateFolderDialog
          parentPath={path}
          onClose={() => setCreateFolderOpen(false)}
          onCreated={() => {
            setCreateFolderOpen(false)
            setReloadTick((tick) => tick + 1)
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

