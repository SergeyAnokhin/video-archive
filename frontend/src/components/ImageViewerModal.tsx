import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronLeft, ChevronRight, Info, X } from 'lucide-react'
import type { FileEntry } from '../types/api'
import { FolderQuickActions } from './FolderQuickActions'
import { QuickTagAdd } from './QuickTagAdd'
import { UserDefinedTagButton } from './UserDefinedTagButton'
import './ImageViewerModal.css'

interface ImageViewerModalProps {
  file: FileEntry
  onClose: () => void
  onMoved?: () => void
  onOpenInfo?: () => void
  onTagAdded?: () => void
  hasPrev?: boolean
  hasNext?: boolean
  onPrev?: () => void
  onNext?: () => void
}

export function ImageViewerModal({
  file,
  onClose,
  onMoved,
  onOpenInfo,
  onTagAdded,
  hasPrev,
  hasNext,
  onPrev,
  onNext,
}: ImageViewerModalProps) {
  const { t } = useTranslation()

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose()
      } else if (event.key === 'ArrowLeft' && hasPrev && onPrev) {
        onPrev()
      } else if (event.key === 'ArrowRight' && hasNext && onNext) {
        onNext()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose, hasPrev, hasNext, onPrev, onNext])

  return (
    <div className="image-viewer-overlay" role="dialog" aria-modal="true" aria-label={file.file_name} onClick={onClose}>
      <div className="image-viewer-overlay__top-left" onClick={(event) => event.stopPropagation()}>
        {onMoved && <FolderQuickActions fileId={file.id} onMoved={onMoved} />}
        <div className="image-viewer-overlay__quick-actions">
          {onOpenInfo && (
            <button
              type="button"
              className="image-viewer-overlay__info-toggle"
              aria-label={t('imageViewerModal.info')}
              title={t('imageViewerModal.info')}
              onClick={onOpenInfo}
            >
              <Info size={16} />
            </button>
          )}
          <QuickTagAdd fileId={file.id} onTagAdded={onTagAdded} />
          <UserDefinedTagButton fileId={file.id} onTagAdded={onTagAdded} />
        </div>
      </div>

      <div className="image-viewer-overlay__top-right" onClick={(event) => event.stopPropagation()}>
        <button
          type="button"
          className="image-viewer-overlay__close"
          aria-label={t('imageViewerModal.close')}
          onClick={onClose}
        >
          <X size={20} />
        </button>
      </div>

      {hasPrev && onPrev && (
        <div
          className="image-viewer-overlay__nav-zone image-viewer-overlay__nav-zone--prev"
          role="button"
          tabIndex={0}
          aria-label={t('imageViewerModal.previous')}
          title={t('imageViewerModal.previous')}
          onClick={(event) => {
            event.stopPropagation()
            onPrev()
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault()
              onPrev()
            }
          }}
        >
          <span className="image-viewer-overlay__nav" aria-hidden="true">
            <ChevronLeft size={24} />
          </span>
        </div>
      )}

      {hasNext && onNext && (
        <div
          className="image-viewer-overlay__nav-zone image-viewer-overlay__nav-zone--next"
          role="button"
          tabIndex={0}
          aria-label={t('imageViewerModal.next')}
          title={t('imageViewerModal.next')}
          onClick={(event) => {
            event.stopPropagation()
            onNext()
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault()
              onNext()
            }
          }}
        >
          <span className="image-viewer-overlay__nav" aria-hidden="true">
            <ChevronRight size={24} />
          </span>
        </div>
      )}

      <img
        className="image-viewer-overlay__image"
        src={`/api/files/${file.id}/stream`}
        alt={file.file_name}
        onClick={(event) => event.stopPropagation()}
      />
    </div>
  )
}
