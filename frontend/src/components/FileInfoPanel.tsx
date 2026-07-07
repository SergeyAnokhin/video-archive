import { useTranslation } from 'react-i18next'
import { Copy, Film, FolderInput, Images, Tags, Trash2, Wand2, X } from 'lucide-react'
import { formatSize } from '../utils/format'
import type { FileEntry } from '../types/api'
import './ConvertDialog.css'
import './FileInfoPanel.css'

interface FileInfoPanelProps {
  file: FileEntry
  previewsVisible: boolean
  previewing: boolean
  tagging: boolean
  onClose: () => void
  onPreview: () => void
  onTag: () => void
  onConvert: () => void
  onSimilar: () => void
  onDelete: () => void
  onMove: () => void
}

export function FileInfoPanel({
  file,
  previewsVisible,
  previewing,
  tagging,
  onClose,
  onPreview,
  onTag,
  onConvert,
  onSimilar,
  onDelete,
  onMove,
}: FileInfoPanelProps) {
  const { t } = useTranslation()
  const showThumbnail = previewsVisible && file.is_video_supported && file.has_preview_asset

  function handleDelete() {
    if (window.confirm(t('library.confirmDeleteFile', { name: file.file_name }))) {
      onDelete()
    }
  }

  return (
    <div className="convert-dialog-overlay" onClick={onClose}>
      <div
        className="convert-dialog file-info-panel"
        role="dialog"
        aria-modal="true"
        aria-label={file.file_name}
        onClick={(event) => event.stopPropagation()}
      >
        <button
          type="button"
          className="file-info-panel__close"
          aria-label={t('playbackModal.close')}
          title={t('playbackModal.close')}
          onClick={onClose}
        >
          <X size={20} />
        </button>

        <h2 className="convert-dialog__title">{file.file_name}</h2>

        <div className="file-info-panel__thumb">
          {showThumbnail ? (
            <img src={`/api/files/${file.id}/preview.jpg`} alt="" className="file-info-panel__thumb-img" />
          ) : (
            <Film size={40} />
          )}
        </div>

        <p className="convert-dialog__hint">{formatSize(file.size_bytes)}</p>

        <ul className="file-info-panel__status">
          <li className="file-info-panel__status-item">
            <span
              className={`file-info-panel__dot ${
                file.converted_at ? 'file-info-panel__dot--done' : 'file-info-panel__dot--conversion'
              }`}
            />
            {t(file.converted_at ? 'library.statusConvertedYes' : 'library.statusConvertedNo')}
          </li>
          <li className="file-info-panel__status-item">
            <span
              className={`file-info-panel__dot ${
                file.has_preview_asset ? 'file-info-panel__dot--done' : 'file-info-panel__dot--preview'
              }`}
            />
            {t(file.has_preview_asset ? 'library.statusPreviewYes' : 'library.statusPreviewNo')}
          </li>
          <li className="file-info-panel__status-item">
            <span
              className={`file-info-panel__dot ${
                file.tagged_at ? 'file-info-panel__dot--done' : 'file-info-panel__dot--tag'
              }`}
            />
            {t(file.tagged_at ? 'library.statusTaggedYes' : 'library.statusTaggedNo')}
          </li>
          {file.is_variant && (
            <li className="file-info-panel__status-item">
              <span className="file-info-panel__dot file-info-panel__dot--done" />
              {t('indicators.fileIsVariant')}
            </li>
          )}
          {file.is_original && (
            <li className="file-info-panel__status-item">
              <span className="file-info-panel__dot file-info-panel__dot--done" />
              {t('indicators.fileIsOriginal')}
            </li>
          )}
        </ul>

        <div className="convert-dialog__actions">
          <button type="button" className="convert-dialog__button" onClick={onPreview} disabled={previewing}>
            <Images size={14} /> {t('library.previewFile')}
          </button>
          <button type="button" className="convert-dialog__button" onClick={onTag} disabled={tagging}>
            <Tags size={14} /> {t('library.tagFile')}
          </button>
          <button type="button" className="convert-dialog__button" onClick={onConvert}>
            <Wand2 size={14} /> {t('library.convertFile')}
          </button>
          <button type="button" className="convert-dialog__button" onClick={onSimilar}>
            <Copy size={14} /> {t('library.similar')}
          </button>
          <button type="button" className="convert-dialog__button" onClick={onMove}>
            <FolderInput size={14} /> {t('library.moveFile')}
          </button>
          <button type="button" className="convert-dialog__button" onClick={handleDelete}>
            <Trash2 size={14} /> {t('library.deleteFile')}
          </button>
        </div>
      </div>
    </div>
  )
}
