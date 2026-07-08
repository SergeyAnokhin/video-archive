import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Archive, File as FileIcon, Film, Folder, Info, SlidersHorizontal } from 'lucide-react'
import type { DirectoryEntry, FileEntry } from '../types/api'
import { formatSize } from '../utils/format'
import './LibraryView.css'

export function FolderCard({
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
            src={`/api/directories/preview.gif?path=${encodeURIComponent(dir.path)}`}
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
  onPlay: () => void
  onInfo: () => void
}

export function FileCard({ file, previewsVisible, onPlay, onInfo }: FileCardProps) {
  const { t } = useTranslation()
  const [gifFailed, setGifFailed] = useState(false)
  const showConversionDot = file.is_video_supported && !file.converted_at
  const showPreviewDot = file.is_video_supported && !file.has_preview_asset
  const showThumbnail = previewsVisible && file.is_video_supported && file.has_preview_asset

  return (
    <div className="library-card">
      <div className="library-card__thumb-frame">
        <button type="button" className="library-card__thumb" aria-label={t('library.play')} title={t('library.play')} onClick={onPlay}>
          {showThumbnail ? (
            <img
              src={gifFailed ? `/api/files/${file.id}/preview.jpg` : `/api/files/${file.id}/preview.gif`}
              alt=""
              className="library-card__thumb-img"
              onError={() => setGifFailed(true)}
            />
          ) : file.is_video_supported ? (
            <Film size={28} />
          ) : (
            <FileIcon size={28} />
          )}
        </button>
        <button
          type="button"
          className="library-card__info-btn"
          aria-label={t('library.info')}
          title={t('library.info')}
          onClick={onInfo}
        >
          <Info size={16} />
        </button>
      </div>
      <div className="library-card__name" title={file.file_name}>
        {file.file_name}
      </div>
      <div className="library-card__meta">{formatSize(file.size_bytes)}</div>
      {(showConversionDot || showPreviewDot || file.is_variant || file.is_original) && (
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
          {file.is_variant && (
            <span
              className="library-card__marker library-card__marker--variant"
              title={t('indicators.fileIsVariant')}
            >
              <SlidersHorizontal size={14} />
            </span>
          )}
          {file.is_original && (
            <span
              className="library-card__marker library-card__marker--original"
              title={t('indicators.fileIsOriginal')}
            >
              <Archive size={14} />
            </span>
          )}
        </div>
      )}
    </div>
  )
}
