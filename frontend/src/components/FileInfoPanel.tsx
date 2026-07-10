import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  ChevronLeft,
  ChevronRight,
  Copy,
  Film,
  FolderInput,
  Images,
  SlidersHorizontal,
  Tags,
  Trash2,
  Wand2,
  X,
} from 'lucide-react'
import { formatBitrate, formatDuration, formatSize } from '../utils/format'
import type { FileEntry, FileMediaInfo, FileTagAssignment, TagRun } from '../types/api'
import { FolderQuickActions } from './FolderQuickActions'
import { VariantTagChip } from './LibraryCards'
import './ConvertDialog.css'
import './FileInfoPanel.css'

interface FileInfoPanelProps {
  file: FileEntry
  previewing: boolean
  tagging: boolean
  onClose: () => void
  onPreview: () => void
  onTag: () => void
  onConvert: () => void
  onTune: () => void
  onSimilar: () => void
  onDelete: () => void
  onMove: () => void
  onMoved?: () => void
  hasPrev?: boolean
  hasNext?: boolean
  onPrev?: () => void
  onNext?: () => void
}

export function FileInfoPanel({
  file,
  previewing,
  tagging,
  onClose,
  onPreview,
  onTag,
  onConvert,
  onTune,
  onSimilar,
  onDelete,
  onMove,
  onMoved,
  hasPrev,
  hasNext,
  onPrev,
  onNext,
}: FileInfoPanelProps) {
  const { t } = useTranslation()
  const showThumbnail = file.is_video_supported && file.has_preview_asset
  const [mediaInfo, setMediaInfo] = useState<FileMediaInfo | null>(null)
  const [mediaInfoLoading, setMediaInfoLoading] = useState(true)
  const [tags, setTags] = useState<FileTagAssignment[]>([])
  const [tagRun, setTagRun] = useState<TagRun | null>(null)

  useEffect(() => {
    let cancelled = false
    setMediaInfo(null)
    setMediaInfoLoading(true)
    fetch(`/api/files/${file.id}/media-info`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data: FileMediaInfo | null) => {
        if (!cancelled) {
          setMediaInfo(data)
        }
      })
      .finally(() => {
        if (!cancelled) {
          setMediaInfoLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [file.id])

  useEffect(() => {
    fetch(`/api/files/${file.id}/tags`).then((res) => (res.ok ? res.json() : null)).then((data) => {
      setTags(data?.tags ?? [])
      setTagRun(data?.run ?? null)
    })
  }, [file.id])

  function handleDelete() {
    if (window.confirm(t('library.confirmDeleteFile', { name: file.file_name }))) {
      onDelete()
    }
  }

  const na = t('library.mediaInfoUnavailable')
  const mediaFields: { label: string; value: string }[] = [
    { label: t('library.mediaInfoSize'), value: formatSize(file.size_bytes) },
    {
      label: t('library.mediaInfoResolution'),
      value: mediaInfo?.width && mediaInfo.height ? `${mediaInfo.width}×${mediaInfo.height}` : na,
    },
    { label: t('library.mediaInfoAspectRatio'), value: mediaInfo?.aspect_ratio ?? na },
    { label: t('library.mediaInfoCodec'), value: mediaInfo?.video_codec?.toUpperCase() ?? na },
    { label: t('library.mediaInfoBitrate'), value: mediaInfo?.bit_rate ? formatBitrate(mediaInfo.bit_rate) : na },
    { label: t('library.mediaInfoDuration'), value: mediaInfo?.duration ? formatDuration(mediaInfo.duration) : na },
    { label: t('library.mediaInfoFormat'), value: mediaInfo?.format_name ?? na },
    {
      label: t('library.mediaInfoProfile'),
      value: mediaInfo?.conversion_profile
        ? `${mediaInfo.conversion_profile.name} (${mediaInfo.conversion_profile.video_codec.toUpperCase()}, CRF ${mediaInfo.conversion_profile.crf})`
        : na,
    },
  ]

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

        {onMoved && (
          <div className="file-info-panel__folder-actions">
            <FolderQuickActions fileId={file.id} onMoved={onMoved} />
          </div>
        )}

        {(hasPrev || hasNext) && (
          <div className="file-info-panel__nav-group">
            <button
              type="button"
              className="file-info-panel__nav"
              aria-label={t('playbackModal.previous')}
              title={t('playbackModal.previous')}
              onClick={onPrev}
              disabled={!hasPrev || !onPrev}
            >
              <ChevronLeft size={16} />
            </button>
            <button
              type="button"
              className="file-info-panel__nav"
              aria-label={t('playbackModal.next')}
              title={t('playbackModal.next')}
              onClick={onNext}
              disabled={!hasNext || !onNext}
            >
              <ChevronRight size={16} />
            </button>
          </div>
        )}

        <h2 className="convert-dialog__title">{file.file_name}</h2>

        <div className="file-info-panel__body">
          <div className="file-info-panel__thumb">
            {showThumbnail ? (
              <img src={`/api/files/${file.id}/preview.jpg`} alt="" className="file-info-panel__thumb-img" />
            ) : (
              <Film size={40} />
            )}
          </div>

          <div className="file-info-panel__details">
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
                  {file.variant_tags && file.variant_tags.length > 0 && (
                    <span className="file-info-panel__variant-tags">
                      {file.variant_tags.map((tag, index) => (
                        <VariantTagChip key={index} tag={tag} />
                      ))}
                    </span>
                  )}
                </li>
              )}
              {file.is_original && (
                <li className="file-info-panel__status-item">
                  <span className="file-info-panel__dot file-info-panel__dot--done" />
                  {t('indicators.fileIsOriginal')}
                </li>
              )}
            </ul>

            <dl className={`file-info-panel__media-grid ${mediaInfoLoading ? 'file-info-panel__media-grid--loading' : ''}`}>
              {mediaFields.map((field) => (
                <div key={field.label} className="file-info-panel__media-field">
                  <dt>{field.label}</dt>
                  <dd>{field.value}</dd>
                </div>
              ))}
            </dl>
            {tags.length > 0 && (
              <section className="file-info-panel__tags">
                <strong>{t('library.detectedTags')}</strong>
                <div className="file-info-panel__tag-list">
                  {tags.map((tag) => <span key={tag.tag_id} className="library-card__tag">{tag.display_name}</span>)}
                </div>
                {tagRun && <p className="file-info-panel__tag-source">{t('library.taggedBy', { provider: tagRun.provider_name, model: tagRun.model_name || t('library.providerDefault'), mode: tagRun.execution_mode })}</p>}
                {tagRun && <details><summary>{t('library.modelResponse')}</summary><pre>{tagRun.response_payload}</pre></details>}
              </section>
            )}
          </div>
        </div>

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
          <button type="button" className="convert-dialog__button" onClick={onTune}>
            <SlidersHorizontal size={14} /> {t('library.tuneFile')}
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
