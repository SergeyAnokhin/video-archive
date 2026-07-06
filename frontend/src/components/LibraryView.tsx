import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { File as FileIcon, Film, Folder, RefreshCw, Wand2 } from 'lucide-react'
import { useJobs } from '../context/JobsContext'
import { ConvertDirectoryDialog } from './ConvertDirectoryDialog'
import { FileConvertModal } from './FileConvertModal'
import type { DirectoryChildrenResponse, DirectoryEntry, FileEntry } from '../types/api'
import './LibraryView.css'

interface LibraryViewProps {
  path: string
  onNavigate: (path: string) => void
}

export function LibraryView({ path, onNavigate }: LibraryViewProps) {
  const { t } = useTranslation()
  const { refresh: refreshJobs } = useJobs()
  const [data, setData] = useState<DirectoryChildrenResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [rescanning, setRescanning] = useState(false)
  const [convertDirOpen, setConvertDirOpen] = useState(false)
  const [convertFile, setConvertFile] = useState<FileEntry | null>(null)

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
            <FolderCard key={dir.path} dir={dir} onOpen={() => onNavigate(dir.path)} />
          ))}
          {data.files.map((file) => (
            <FileCard key={file.id} file={file} onConvert={() => setConvertFile(file)} />
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
    </div>
  )
}

function FolderCard({ dir, onOpen }: { dir: DirectoryEntry; onOpen: () => void }) {
  const { t } = useTranslation()
  const status = dir.status
  const showConversionDot = Boolean(status && !status.conversion_complete)
  const showPreviewDot = Boolean(status && !status.preview_complete)

  return (
    <button type="button" className="library-card library-card--folder" onClick={onOpen}>
      <div className="library-card__thumb">
        <Folder size={28} />
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

function FileCard({ file, onConvert }: { file: FileEntry; onConvert: () => void }) {
  const { t } = useTranslation()
  const showConversionDot = file.is_video_supported && !file.converted_at
  const showPreviewDot = file.is_video_supported && !file.has_preview_asset

  return (
    <div className="library-card">
      <div className="library-card__thumb">
        {file.is_video_supported ? <Film size={28} /> : <FileIcon size={28} />}
      </div>
      <div className="library-card__name" title={file.file_name}>
        {file.file_name}
      </div>
      <div className="library-card__meta">{formatSize(file.size_bytes)}</div>
      {file.is_video_supported && (
        <button
          type="button"
          className="library-card__convert-btn"
          aria-label={t('library.convertFile')}
          title={t('library.convertFile')}
          onClick={onConvert}
        >
          <Wand2 size={14} />
        </button>
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
