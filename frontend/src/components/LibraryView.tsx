import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Copy,
  File as FileIcon,
  Film,
  Folder,
  Images,
  MoreVertical,
  Play,
  RefreshCw,
  Search,
  Tags,
  Wand2,
  X,
} from 'lucide-react'
import { useJobs } from '../context/JobsContext'
import { usePreviewVisibility } from '../context/PreviewVisibilityContext'
import { useTags } from '../context/TagsContext'
import { ConvertDirectoryDialog } from './ConvertDirectoryDialog'
import { FileConvertModal } from './FileConvertModal'
import { PlaybackModal } from './PlaybackModal'
import { PreviewDirectoryDialog } from './PreviewDirectoryDialog'
import { SimilarFilesModal } from './SimilarFilesModal'
import { TagDirectoryDialog } from './TagDirectoryDialog'
import type { DirectoryChildrenResponse, DirectoryEntry, FileEntry, Tag } from '../types/api'
import './LibraryView.css'

interface LibraryViewProps {
  path: string
  onNavigate: (path: string) => void
}

interface ActiveSearch {
  kind: 'tag' | 'name'
  label: string
  value: string
}

export function LibraryView({ path, onNavigate }: LibraryViewProps) {
  const { t } = useTranslation()
  const { refresh: refreshJobs } = useJobs()
  const { previewsVisible } = usePreviewVisibility()
  const [data, setData] = useState<DirectoryChildrenResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [rescanning, setRescanning] = useState(false)
  const [convertDirOpen, setConvertDirOpen] = useState(false)
  const [convertFile, setConvertFile] = useState<FileEntry | null>(null)
  const [previewDirOpen, setPreviewDirOpen] = useState(false)
  const [previewingFileId, setPreviewingFileId] = useState<string | null>(null)
  const [tagDirOpen, setTagDirOpen] = useState(false)
  const [taggingFileId, setTaggingFileId] = useState<string | null>(null)
  const [playingFile, setPlayingFile] = useState<FileEntry | null>(null)
  const [similarFile, setSimilarFile] = useState<FileEntry | null>(null)
  const [activeSearch, setActiveSearch] = useState<ActiveSearch | null>(null)
  const [searchResults, setSearchResults] = useState<FileEntry[] | null>(null)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [overflowOpen, setOverflowOpen] = useState(false)
  const overflowRef = useRef<HTMLDivElement | null>(null)

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
  }, [path, activeSearch])

  const segments = path ? path.split('/') : []

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

  return (
    <div className="library-view">
      <div className="library-view__toolbar">
        <nav className="library-view__breadcrumb" aria-label={t('library.breadcrumb')}>
          <button type="button" onClick={() => onNavigate('')}>
            {t('library.root')}
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

        <LibrarySearchBox
          onSearch={(search) => setActiveSearch(search)}
          onClear={() => setActiveSearch(null)}
        />

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

      {activeSearch && (
        <div className="library-view__search-banner">
          <span>{t('library.searchResultsFor', { query: activeSearch.label })}</span>
          <button type="button" className="library-view__icon-btn" onClick={() => setActiveSearch(null)}>
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
              {searchResults.map((file) => (
                <FileCard
                  key={file.id}
                  file={file}
                  previewsVisible={previewsVisible}
                  previewing={previewingFileId === file.id}
                  tagging={taggingFileId === file.id}
                  onConvert={() => setConvertFile(file)}
                  onPreview={() => void handlePreviewFile(file.id)}
                  onTag={() => void handleTagFile(file.id)}
                  onPlay={() => setPlayingFile(file)}
                  onSimilar={() => setSimilarFile(file)}
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
                <FolderCard key={dir.path} dir={dir} previewsVisible={previewsVisible} onOpen={() => onNavigate(dir.path)} />
              ))}
              {data.files.map((file) => (
                <FileCard
                  key={file.id}
                  file={file}
                  previewsVisible={previewsVisible}
                  previewing={previewingFileId === file.id}
                  tagging={taggingFileId === file.id}
                  onConvert={() => setConvertFile(file)}
                  onPreview={() => void handlePreviewFile(file.id)}
                  onTag={() => void handleTagFile(file.id)}
                  onPlay={() => setPlayingFile(file)}
                  onSimilar={() => setSimilarFile(file)}
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
    </div>
  )
}

interface LibrarySearchBoxProps {
  onSearch: (search: ActiveSearch) => void
  onClear: () => void
}

function LibrarySearchBox({ onSearch, onClear }: LibrarySearchBoxProps) {
  const { t } = useTranslation()
  const { tags } = useTags()
  const [value, setValue] = useState('')
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const prefix = value.trim().toLowerCase()
  const suggestions: Tag[] = prefix
    ? tags.filter((tag) => tag.tag_key.startsWith(prefix)).slice(0, 8)
    : []

  function selectTag(tag: Tag) {
    setValue(tag.display_name)
    setOpen(false)
    onSearch({ kind: 'tag', label: tag.display_name, value: tag.tag_key })
  }

  function submitFreeText() {
    if (!value.trim()) {
      return
    }
    setOpen(false)
    onSearch({ kind: 'name', label: value.trim(), value: value.trim() })
  }

  function clear() {
    setValue('')
    setOpen(false)
    onClear()
  }

  return (
    <div className="library-view__search" ref={containerRef}>
      <Search size={14} className="library-view__search-icon" />
      <input
        type="text"
        className="library-view__search-input"
        placeholder={t('library.searchPlaceholder')}
        value={value}
        onChange={(event) => {
          setValue(event.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            submitFreeText()
          } else if (event.key === 'Escape') {
            setOpen(false)
          }
        }}
      />
      {value && (
        <button
          type="button"
          className="library-view__search-clear"
          aria-label={t('library.searchClear')}
          onClick={clear}
        >
          <X size={12} />
        </button>
      )}
      {open && suggestions.length > 0 && (
        <ul className="library-view__search-suggestions">
          {suggestions.map((tag) => (
            <li key={tag.id}>
              <button type="button" onClick={() => selectTag(tag)}>
                {tag.display_name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function FolderCard({
  dir,
  previewsVisible,
  onOpen,
}: {
  dir: DirectoryEntry
  previewsVisible: boolean
  onOpen: () => void
}) {
  const { t } = useTranslation()
  const status = dir.status
  const showConversionDot = Boolean(status && !status.conversion_complete)
  const showPreviewDot = Boolean(status && !status.preview_complete)
  const showThumbnail = previewsVisible && dir.has_folder_preview

  return (
    <button type="button" className="library-card library-card--folder" onClick={onOpen}>
      <div className="library-card__thumb">
        {showThumbnail ? (
          <img
            src={`/api/directories/preview.jpg?path=${encodeURIComponent(dir.path)}`}
            alt=""
            className="library-card__thumb-img"
          />
        ) : (
          <Folder size={28} />
        )}
      </div>
      <div className="library-card__name">{dir.name}</div>
      {(showConversionDot || showPreviewDot) && (
        <div className="library-card__badges">
          {showConversionDot && (
            <span
              className="library-card__dot library-card__dot--conversion"
              title={t('indicators.conversionIncomplete', {
                converted: status?.converted_count,
                total: status?.total_supported_files,
              })}
            />
          )}
          {showPreviewDot && (
            <span
              className="library-card__dot library-card__dot--preview"
              title={t('indicators.previewIncomplete', {
                generated: status?.preview_count,
                total: status?.total_supported_files,
              })}
            />
          )}
        </div>
      )}
    </button>
  )
}

interface FileCardProps {
  file: FileEntry
  previewsVisible: boolean
  previewing: boolean
  tagging: boolean
  onConvert: () => void
  onPreview: () => void
  onTag: () => void
  onPlay: () => void
  onSimilar: () => void
}

function FileCard({
  file,
  previewsVisible,
  previewing,
  tagging,
  onConvert,
  onPreview,
  onTag,
  onPlay,
  onSimilar,
}: FileCardProps) {
  const { t } = useTranslation()
  const showConversionDot = file.is_video_supported && !file.converted_at
  const showPreviewDot = file.is_video_supported && !file.has_preview_asset
  const showThumbnail = previewsVisible && file.is_video_supported && file.has_preview_asset

  return (
    <div className="library-card">
      <div className="library-card__thumb">
        {showThumbnail ? (
          <img src={`/api/files/${file.id}/preview.jpg`} alt="" className="library-card__thumb-img" />
        ) : file.is_video_supported ? (
          <Film size={28} />
        ) : (
          <FileIcon size={28} />
        )}
      </div>
      <div className="library-card__name" title={file.file_name}>
        {file.file_name}
      </div>
      <div className="library-card__meta">{formatSize(file.size_bytes)}</div>
      {file.is_video_supported && (
        <div className="library-card__file-actions">
          <button
            type="button"
            className="library-card__convert-btn"
            aria-label={t('library.play')}
            title={t('library.play')}
            onClick={onPlay}
          >
            <Play size={14} />
          </button>
          <button
            type="button"
            className="library-card__convert-btn"
            aria-label={t('library.previewFile')}
            title={t('library.previewFile')}
            onClick={onPreview}
            disabled={previewing}
          >
            <Images size={14} />
          </button>
          <button
            type="button"
            className="library-card__convert-btn"
            aria-label={t('library.tagFile')}
            title={t('library.tagFile')}
            onClick={onTag}
            disabled={tagging}
          >
            <Tags size={14} />
          </button>
          <button
            type="button"
            className="library-card__convert-btn"
            aria-label={t('library.convertFile')}
            title={t('library.convertFile')}
            onClick={onConvert}
          >
            <Wand2 size={14} />
          </button>
          <button
            type="button"
            className="library-card__convert-btn"
            aria-label={t('library.similar')}
            title={t('library.similar')}
            onClick={onSimilar}
          >
            <Copy size={14} />
          </button>
        </div>
      )}
      {(showConversionDot || showPreviewDot) && (
        <div className="library-card__badges">
          {showConversionDot && (
            <span
              className="library-card__dot library-card__dot--conversion"
              title={t('indicators.fileNotConverted')}
            />
          )}
          {showPreviewDot && (
            <span
              className="library-card__dot library-card__dot--preview"
              title={t('indicators.fileNoPreview')}
            />
          )}
        </div>
      )}
    </div>
  )
}

function formatSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`
  }
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let unitIndex = 0
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex += 1
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`
}
