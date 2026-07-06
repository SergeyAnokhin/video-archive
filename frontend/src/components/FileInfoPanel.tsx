import { useTranslation } from 'react-i18next'
import { Copy, Film, Images, Tags, Wand2 } from 'lucide-react'
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
}: FileInfoPanelProps) {
  const { t } = useTranslation()
  const showThumbnail = previewsVisible && file.is_video_supported && file.has_preview_asset

  return (
    <div className="convert-dialog-overlay" onClick={onClose}>
      <div
        className="convert-dialog file-info-panel"
        role="dialog"
        aria-modal="true"
        aria-label={file.file_name}
        onClick={(event) => event.stopPropagation()}
      >
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
          <li>{t(file.converted_at ? 'library.statusConvertedYes' : 'library.statusConvertedNo')}</li>
          <li>{t(file.has_preview_asset ? 'library.statusPreviewYes' : 'library.statusPreviewNo')}</li>
          <li>{t(file.tagged_at ? 'library.statusTaggedYes' : 'library.statusTaggedNo')}</li>
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
        </div>

        <div className="convert-dialog__actions">
          <button type="button" className="convert-dialog__button" onClick={onClose}>
            {t('playbackModal.close')}
          </button>
        </div>
      </div>
    </div>
  )
}
