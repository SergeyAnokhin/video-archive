import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { File as FileIcon, Film, Folder, Images, RefreshCw, Wand2 } from 'lucide-react'
import { useJobs } from '../context/JobsContext'
import { usePreviewVisibility } from '../context/PreviewVisibilityContext'
import { ConvertDirectoryDialog } from './ConvertDirectoryDialog'
import { FileConvertModal } from './FileConvertModal'
import { PreviewDirectoryDialog } from './PreviewDirectoryDialog'
import type { DirectoryChildrenResponse, DirectoryEntry, FileEntry } from '../types/api'
import './LibraryView.css'

interface LibraryViewProps {
  path: string
  onNavigate: (path: string) => void
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

  useEffect(() => {
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
  }, [path])

  const segments = path ? path.split('/') : []

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

        <button
          type="button"
          className="library-view__icon-btn"
          aria-label={t('library.convert')}
          title={t('library.convert')}
          onClick={() => setConvertDirOpen(true)}
        >
          <Wand2 size={16} />
        </button>

        <button
          type="button"
          className="library-view__icon-btn"
          aria-label={t('library.preview')}
          title={t('library.preview')}
          onClick={() => setPreviewDirOpen(true)}
        >
          <Images size={16} />
        </button>
      </div>

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
              onConvert={() => setConvertFile(file)}
              onPreview={() => void handlePreviewFile(file.id)}
            />
          ))}
        </div>
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
  onConvert: () => void
  onPreview: () => void
}

function FileCard({ file, previewsVisible, previewing, onConvert, onPreview }: FileCardProps) {
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
            aria-label={t('library.convertFile')}
            title={t('library.convertFile')}
            onClick={onConvert}
          >
            <Wand2 size={14} />
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
