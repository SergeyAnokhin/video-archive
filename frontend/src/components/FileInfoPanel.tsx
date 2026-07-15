import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import { useTranslation } from 'react-i18next'
import {
  ChevronLeft,
  ChevronRight,
  Copy,
  Film,
  FolderInput,
  Images,
  Plus,
  SlidersHorizontal,
  Tags,
  Trash2,
  Wand2,
  X,
} from 'lucide-react'
import { formatBitrate, formatDuration, formatSize } from '../utils/format'
import type { FileEntry, FileMediaInfo, FileTagAssignment, Tag } from '../types/api'
import { FolderQuickActions } from './FolderQuickActions'
import { VariantTagChip } from './LibraryCards'
import { TagBadge } from './TagBadge'
import { UserDefinedTagButton } from './UserDefinedTagButton'
import './ConvertDialog.css'
import './FileInfoPanel.css'

interface FileInfoPanelProps {
  file: FileEntry
  previewing: boolean
  onClose: () => void
  onPreview: () => void
  onTag: () => void
  onConvert: () => void
  onTune: () => void
  onSimilar: () => void
  onDelete: () => void
  onMove: () => void
  onMoved?: () => void
  onTagsChanged?: () => void
  hasPrev?: boolean
  hasNext?: boolean
  onPrev?: () => void
  onNext?: () => void
}

const SPLIT_STORAGE_KEY = 'video-archive:file-info-split'
const SPLIT_MIN = 25
const SPLIT_MAX = 85
const SPLIT_DEFAULT = 70

function clampSplit(value: number): number {
  return Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, value))
}

function detectInitialSplit(): number {
  const stored = Number(window.localStorage.getItem(SPLIT_STORAGE_KEY))
  return Number.isFinite(stored) && stored > 0 ? clampSplit(stored) : SPLIT_DEFAULT
}

export function FileInfoPanel({
  file,
  previewing,
  onClose,
  onPreview,
  onTag,
  onConvert,
  onTune,
  onSimilar,
  onDelete,
  onMove,
  onMoved,
  onTagsChanged,
  hasPrev,
  hasNext,
  onPrev,
  onNext,
}: FileInfoPanelProps) {
  const { t } = useTranslation()
  const showThumbnail = file.is_video_supported && file.has_preview_asset
  const bodyRef = useRef<HTMLDivElement | null>(null)
  const draggingRef = useRef(false)
  const [splitPercent, setSplitPercent] = useState<number>(() => detectInitialSplit())
  const [mediaInfo, setMediaInfo] = useState<FileMediaInfo | null>(null)
  const [mediaInfoLoading, setMediaInfoLoading] = useState(true)
  const [tags, setTags] = useState<FileTagAssignment[]>([])
  const [tagsLoading, setTagsLoading] = useState(true)
  const [tagInput, setTagInput] = useState('')
  const [addingTag, setAddingTag] = useState(false)
  const [tagError, setTagError] = useState<string | null>(null)
  const [tagOptions, setTagOptions] = useState<Tag[]>([])

  const refreshTagOptions = useCallback(async () => {
    const res = await fetch('/api/tags/used?limit=500')
    if (res.ok) {
      const data: { tags: Tag[] } = await res.json()
      setTagOptions(data.tags)
    }
  }, [])

  useEffect(() => {
    void refreshTagOptions()
  }, [refreshTagOptions])

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
    let cancelled = false
    setTags([])
    setTagsLoading(true)
    fetch(`/api/files/${file.id}/tags`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data: { tags: FileTagAssignment[] } | null) => {
        if (!cancelled) {
          setTags(data?.tags ?? [])
        }
      })
      .finally(() => {
        if (!cancelled) {
          setTagsLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [file.id])

  const refetchTags = useCallback(async () => {
    setTagsLoading(true)
    try {
      const res = await fetch(`/api/files/${file.id}/tags`)
      const data: { tags: FileTagAssignment[] } | null = res.ok ? await res.json() : null
      setTags(data?.tags ?? [])
    } finally {
      setTagsLoading(false)
    }
  }, [file.id])

  async function handleAddTag(event: FormEvent) {
    event.preventDefault()
    const displayName = tagInput.trim()
    if (!displayName) {
      return
    }
    setAddingTag(true)
    setTagError(null)
    try {
      const res = await fetch(`/api/files/${file.id}/tags`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: displayName }),
      })
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`)
      }
      setTagInput('')
      await refetchTags()
      void refreshTagOptions()
      onTagsChanged?.()
    } catch {
      setTagError(t('library.tagsAddError'))
    } finally {
      setAddingTag(false)
    }
  }

  async function handleRemoveTag(tagId: string) {
    setTagError(null)
    try {
      const res = await fetch(`/api/files/${file.id}/tags/${tagId}`, { method: 'DELETE' })
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`)
      }
      setTags((current) => current.filter((tag) => tag.tag_id !== tagId))
      onTagsChanged?.()
    } catch {
      setTagError(t('library.tagsRemoveError'))
    }
  }

  const handleDividerPointerDown = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault()
    const body = bodyRef.current
    if (!body) {
      return
    }
    draggingRef.current = true
    const rect = body.getBoundingClientRect()

    function handlePointerMove(moveEvent: PointerEvent) {
      if (!draggingRef.current) {
        return
      }
      const ratio = ((moveEvent.clientX - rect.left) / rect.width) * 100
      setSplitPercent(clampSplit(ratio))
    }

    function handlePointerUp() {
      draggingRef.current = false
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', handlePointerUp)
      setSplitPercent((current) => {
        window.localStorage.setItem(SPLIT_STORAGE_KEY, String(current))
        return current
      })
    }

    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', handlePointerUp)
  }, [])

  function handleDividerKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    let delta = 0
    if (event.key === 'ArrowLeft') {
      delta = -2
    } else if (event.key === 'ArrowRight') {
      delta = 2
    } else {
      return
    }
    event.preventDefault()
    setSplitPercent((current) => {
      const next = clampSplit(current + delta)
      window.localStorage.setItem(SPLIT_STORAGE_KEY, String(next))
      return next
    })
  }

  const tagModels = Array.from(
    new Set(
      tags
        .filter((tag) => tag.provider_name !== 'manual' && tag.provider_name !== 'tuning')
        .map((tag) => tag.model_name ?? tag.provider_name)
        .filter((value): value is string => Boolean(value)),
    ),
  )

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

        <div
          className="file-info-panel__body"
          ref={bodyRef}
          style={{ '--fip-split': `${splitPercent}%` } as CSSProperties}
        >
          <div className="file-info-panel__thumb">
            {file.is_image_supported ? (
              <img src={`/api/files/${file.id}/stream`} alt="" className="file-info-panel__thumb-img" />
            ) : showThumbnail ? (
              <img src={`/api/files/${file.id}/preview.jpg`} alt="" className="file-info-panel__thumb-img" />
            ) : (
              <Film size={40} />
            )}
          </div>

          <div
            className="file-info-panel__divider"
            role="separator"
            aria-orientation="vertical"
            aria-label={t('library.resizePanels')}
            title={t('library.resizePanels')}
            tabIndex={0}
            onPointerDown={handleDividerPointerDown}
            onKeyDown={handleDividerKeyDown}
          />

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
                </li>
              )}
              {file.is_original && (
                <li className="file-info-panel__status-item">
                  <span className="file-info-panel__dot file-info-panel__dot--done" />
                  {t('indicators.fileIsOriginal')}
                </li>
              )}
            </ul>

            {file.is_variant && file.variant_tags && file.variant_tags.length > 0 && (
              <div className="file-info-panel__tags-section">
                <h3 className="file-info-panel__tags-title">{t('library.tuningSectionTitle')}</h3>
                <div className="file-info-panel__variant-tags">
                  {file.variant_tags.map((tag, index) => (
                    <VariantTagChip key={index} tag={tag} />
                  ))}
                </div>
              </div>
            )}

            <div className="file-info-panel__tags-section">
              <h3 className="file-info-panel__tags-title">{t('library.tagsSectionTitle')}</h3>
              {!tagsLoading && tags.length === 0 && (
                <p className="file-info-panel__tags-empty">{t('library.tagsEmpty')}</p>
              )}
              {tags.length > 0 && (
                <>
                  <ul className="file-info-panel__tags-list">
                    {tags.map((tag) => (
                      <li key={tag.tag_id} className="file-info-panel__tags-row">
                        <TagBadge
                          displayName={tag.display_name}
                          color={tag.color}
                          scoreLabel={`${tag.score}%`}
                          title={
                            tag.provider_name === 'manual'
                              ? t('library.tagsManualLabel')
                              : tag.provider_name === 'tuning'
                                ? t('library.tagsTuningLabel')
                                : undefined
                          }
                          onRemove={() => handleRemoveTag(tag.tag_id)}
                          removeLabel={t('library.tagsRemove', { name: tag.display_name })}
                        />
                      </li>
                    ))}
                  </ul>
                  {tagModels.length > 0 && (
                    <p className="file-info-panel__tags-model">
                      {t('library.tagsModelLabel', { model: tagModels.join(', ') })}
                    </p>
                  )}
                </>
              )}
              <form className="file-info-panel__tags-add" onSubmit={handleAddTag}>
                <input
                  type="text"
                  list="file-info-panel-tag-options"
                  className="file-info-panel__tags-input"
                  placeholder={t('library.tagsAddPlaceholder')}
                  value={tagInput}
                  onChange={(event) => setTagInput(event.target.value)}
                />
                <datalist id="file-info-panel-tag-options">
                  {tagOptions.map((option) => (
                    <option key={option.id} value={option.display_name} />
                  ))}
                </datalist>
                <button
                  type="submit"
                  className="file-info-panel__tags-add-btn"
                  disabled={!tagInput.trim() || addingTag}
                  aria-label={t('library.tagsAddButton')}
                  title={t('library.tagsAddButton')}
                >
                  <Plus size={14} />
                </button>
              </form>
              {tagError && <p className="file-info-panel__tags-error">{tagError}</p>}
              <UserDefinedTagButton
                fileId={file.id}
                variant="panel"
                onTagAdded={() => {
                  void refetchTags()
                  onTagsChanged?.()
                }}
              />
            </div>

            <dl className={`file-info-panel__media-grid ${mediaInfoLoading ? 'file-info-panel__media-grid--loading' : ''}`}>
              {mediaFields.map((field) => (
                <div key={field.label} className="file-info-panel__media-field">
                  <dt>{field.label}</dt>
                  <dd>{field.value}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>

        <div className="convert-dialog__actions">
          {file.is_video_supported && (
            <button type="button" className="convert-dialog__button" onClick={onPreview} disabled={previewing}>
              <Images size={14} /> {t('library.previewFile')}
            </button>
          )}
          <button type="button" className="convert-dialog__button" onClick={onTag}>
            <Tags size={14} /> {t('library.tagFile')}
          </button>
          {file.is_video_supported && (
            <button type="button" className="convert-dialog__button" onClick={onConvert}>
              <Wand2 size={14} /> {t('library.convertFile')}
            </button>
          )}
          {file.is_video_supported && (
            <button type="button" className="convert-dialog__button" onClick={onTune}>
              <SlidersHorizontal size={14} /> {t('library.tuneFile')}
            </button>
          )}
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
