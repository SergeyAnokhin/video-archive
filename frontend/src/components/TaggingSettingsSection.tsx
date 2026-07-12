import { Check, Copy, Eye, Maximize2, Plus, X } from 'lucide-react'
import { useEffect, useState, type CSSProperties } from 'react'
import { useTranslation } from 'react-i18next'
import { useTags } from '../context/TagsContext'
import type { Tag, TaggingSettings } from '../types/api'
import { loadPreviewSampleFileIds } from '../utils/recentlyViewed'

interface TaggingPreviewImage {
  data_url: string
  width: number
  height: number
}

// Cheerful, high-contrast-on-dark palette (Design System dark surfaces) so
// tags stay easy to tell apart even with 20-30 of them on screen at once.
const TAG_PALETTE = [
  '#ff6b6b',
  '#f59f00',
  '#ffd43b',
  '#69db7c',
  '#38d9a9',
  '#4dabf7',
  '#748ffc',
  '#da77f2',
  '#f783ac',
  '#ff922b',
  '#20c997',
  '#22b8cf',
]

function tagColor(id: string): string {
  let hash = 0
  for (let i = 0; i < id.length; i++) {
    hash = (hash * 31 + id.charCodeAt(i)) | 0
  }
  return TAG_PALETTE[Math.abs(hash) % TAG_PALETTE.length]
}

export function TaggingSettingsSection() {
  const { t } = useTranslation()
  const { tags, refresh: refreshTags } = useTags()
  const [settings, setSettings] = useState<TaggingSettings | null>(null)
  const [newTagName, setNewTagName] = useState('')
  const [tagError, setTagError] = useState<string | null>(null)
  const [editingTagId, setEditingTagId] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const [copied, setCopied] = useState(false)
  const [previewImages, setPreviewImages] = useState<TaggingPreviewImage[] | null>(null)
  const [previewCombined, setPreviewCombined] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [previewFullscreen, setPreviewFullscreen] = useState(false)

  useEffect(() => {
    void (async () => {
      const res = await fetch('/api/tagging-settings')
      if (res.ok) {
        setSettings(await res.json())
      }
    })()
  }, [])

  useEffect(() => {
    if (!previewFullscreen) {
      return
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        // Capture phase + stopPropagation so this closes only the fullscreen
        // overlay, not the Settings modal underneath (which has its own,
        // later-firing bubble-phase Escape listener on window).
        event.stopPropagation()
        setPreviewFullscreen(false)
      }
    }
    window.addEventListener('keydown', handleKeyDown, true)
    return () => window.removeEventListener('keydown', handleKeyDown, true)
  }, [previewFullscreen])

  async function handleAddTag() {
    if (!newTagName.trim()) {
      return
    }
    setTagError(null)
    try {
      const res = await fetch('/api/tags', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: newTagName.trim() }),
      })
      if (!res.ok) {
        const json = await res.json().catch(() => null)
        throw new Error(json?.detail?.error?.message ?? `HTTP ${res.status}`)
      }
      setNewTagName('')
      await refreshTags()
    } catch (err) {
      setTagError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleToggleActive(tag: Tag) {
    await fetch(`/api/tags/${tag.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...tag, is_active: !tag.is_active }),
    })
    await refreshTags()
  }

  async function handleRenameTag(tag: Tag, displayName: string) {
    if (!displayName.trim() || displayName === tag.display_name) {
      return
    }
    await fetch(`/api/tags/${tag.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...tag, display_name: displayName.trim() }),
    })
    await refreshTags()
  }

  async function handleDeleteTag(tag: Tag) {
    await fetch(`/api/tags/${tag.id}`, { method: 'DELETE' })
    await refreshTags()
  }

  async function handleSaveSettings(next: TaggingSettings) {
    const res = await fetch('/api/tagging-settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(next),
    })
    if (res.ok) {
      setSettings(await res.json())
    }
  }

  async function handlePreview() {
    if (!settings) {
      return
    }
    setPreviewLoading(true)
    setPreviewError(null)
    try {
      const [fileId] = await loadPreviewSampleFileIds()
      if (!fileId) {
        throw new Error(t('tagging.previewNoVideo'))
      }
      const res = await fetch('/api/tagging-settings/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_id: fileId,
          sample_frame_count: settings.sample_frame_count,
          combine_into_collage: settings.combine_into_collage,
          image_resolution: settings.image_resolution,
        }),
      })
      if (!res.ok) {
        const json = await res.json().catch(() => null)
        throw new Error(json?.detail?.error?.message ?? `HTTP ${res.status}`)
      }
      const json = (await res.json()) as { images: TaggingPreviewImage[]; combine_into_collage: boolean }
      setPreviewImages(json.images)
      setPreviewCombined(json.combine_into_collage)
    } catch (err) {
      setPreviewImages(null)
      setPreviewError(err instanceof Error ? err.message : String(err))
    } finally {
      setPreviewLoading(false)
    }
  }

  function startEditing(tag: Tag) {
    setEditingTagId(tag.id)
    setEditValue(tag.display_name)
  }

  async function commitEdit(tag: Tag) {
    const value = editValue
    setEditingTagId(null)
    await handleRenameTag(tag, value)
  }

  async function handleCopyAll() {
    const text = tags.map((tag) => tag.display_name).join(', ')
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <section className="settings-modal__section">
      <h3 className="settings-modal__section-title">{t('tagging.title')}</h3>

      <div className="tag-chip-toolbar">
        <p className="tag-chip-toolbar__hint">{t('tagging.vocabularyHint')}</p>
        {tags.length > 0 && (
          <button
            type="button"
            className="settings-modal__option settings-modal__option--icon"
            onClick={() => void handleCopyAll()}
            title={t('tagging.copyAll')}
            aria-label={t('tagging.copyAll')}
          >
            {copied ? <Check size={14} /> : <Copy size={14} />}
          </button>
        )}
      </div>

      {tags.length === 0 && <p className="settings-modal__hint">{t('tagging.vocabularyEmpty')}</p>}

      <div className="tag-chip-list">
        {tags.map((tag) => (
          <span
            key={tag.id}
            className={`tag-chip${tag.is_active ? '' : ' tag-chip--inactive'}`}
            style={{ '--tag-color': tagColor(tag.id) } as CSSProperties}
          >
            {editingTagId === tag.id ? (
              <input
                className="tag-chip__label-input"
                autoFocus
                value={editValue}
                onChange={(event) => setEditValue(event.target.value)}
                onBlur={() => void commitEdit(tag)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') void commitEdit(tag)
                  if (event.key === 'Escape') setEditingTagId(null)
                }}
              />
            ) : (
              <button
                type="button"
                className="tag-chip__label"
                onClick={() => void handleToggleActive(tag)}
                onDoubleClick={() => startEditing(tag)}
                title={tag.is_active ? t('tagging.deactivate') : t('tagging.activate')}
              >
                {tag.display_name}
              </button>
            )}
            <button
              type="button"
              className="tag-chip__remove"
              onClick={() => void handleDeleteTag(tag)}
              aria-label={t('tagging.delete')}
              title={t('tagging.delete')}
            >
              <X size={12} />
            </button>
          </span>
        ))}
      </div>

      <div className="settings-modal__actions">
        <input
          className="settings-modal__input"
          placeholder={t('tagging.newTagPlaceholder')}
          value={newTagName}
          onChange={(event) => setNewTagName(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              void handleAddTag()
            }
          }}
        />
        <button
          type="button"
          className="settings-modal__option settings-modal__option--icon"
          onClick={() => void handleAddTag()}
          aria-label={t('tagging.add')}
          title={t('tagging.add')}
        >
          <Plus size={16} />
        </button>
      </div>
      {tagError && <p className="settings-modal__hint settings-modal__hint--error">{tagError}</p>}

      {settings && (
        <>
          <div className="settings-modal__row">
            <label className="settings-modal__label">
              {t('tagging.sampleFrameCount')}
              <input
                className="settings-modal__input"
                type="number"
                min={1}
                max={16}
                value={settings.sample_frame_count}
                onChange={(event) => setSettings({ ...settings, sample_frame_count: Number(event.target.value) })}
                onBlur={() => void handleSaveSettings(settings)}
              />
            </label>

            <label className="settings-modal__label">
              {t('tagging.topTagCount')}
              <input
                className="settings-modal__input"
                type="number"
                min={1}
                max={50}
                value={settings.top_tag_count}
                onChange={(event) => setSettings({ ...settings, top_tag_count: Number(event.target.value) })}
                onBlur={() => void handleSaveSettings(settings)}
              />
            </label>

            <label className="settings-modal__label">
              {t('tagging.imageResolution')}
              <input
                className="settings-modal__input"
                type="number"
                min={64}
                max={2048}
                step={8}
                value={settings.image_resolution}
                onChange={(event) => setSettings({ ...settings, image_resolution: Number(event.target.value) })}
                onBlur={() => void handleSaveSettings(settings)}
              />
            </label>
          </div>
          <p className="settings-modal__hint">{t('tagging.imageResolutionHint')}</p>

          <label className="settings-modal__field">
            <span className="settings-modal__field-label">{t('tagging.combineIntoCollage')}</span>
            <input
              type="checkbox"
              checked={settings.combine_into_collage}
              onChange={(event) => {
                const next = { ...settings, combine_into_collage: event.target.checked }
                setSettings(next)
                void handleSaveSettings(next)
              }}
            />
          </label>

          <div className="tagging-preview">
            <button
              type="button"
              className="settings-modal__option"
              onClick={() => void handlePreview()}
              disabled={previewLoading}
            >
              <Eye size={14} /> {previewLoading ? t('tagging.previewLoading') : t('tagging.previewButton')}
            </button>
            <p className="settings-modal__hint">{t('tagging.previewHint')}</p>
            {previewError && <p className="settings-modal__hint settings-modal__hint--error">{previewError}</p>}

            {previewImages && previewImages.length > 0 && (
              <div className="tagging-preview__result">
                <button
                  type="button"
                  className="settings-modal__option settings-modal__option--icon tagging-preview__fullscreen-trigger"
                  onClick={() => setPreviewFullscreen(true)}
                  aria-label={t('tagging.previewFullscreen')}
                  title={t('tagging.previewFullscreen')}
                >
                  <Maximize2 size={14} />
                </button>
                {previewCombined ? (
                  <div className="tagging-preview__scroll">
                    <div className="tagging-preview__collage">
                      <img src={previewImages[0].data_url} alt="" width={previewImages[0].width} height={previewImages[0].height} />
                      <span className="tagging-preview__caption">
                        {t('tagging.previewDimensions', {
                          width: previewImages[0].width,
                          height: previewImages[0].height,
                        })}
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="tagging-preview__scroll">
                    <div className="tagging-preview__frames">
                      {previewImages.map((image, index) => (
                        <div key={index} className="tagging-preview__frame">
                          <img src={image.data_url} alt="" width={image.width} height={image.height} />
                          <span className="tagging-preview__caption">
                            {t('tagging.previewDimensions', { width: image.width, height: image.height })}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {previewFullscreen && previewImages && previewImages.length > 0 && (
              <div className="tagging-preview__fullscreen-overlay" onClick={() => setPreviewFullscreen(false)}>
                <div className="tagging-preview__fullscreen-content" onClick={(event) => event.stopPropagation()}>
                  <button
                    type="button"
                    className="tagging-preview__fullscreen-close"
                    aria-label={t('settings.close')}
                    title={t('settings.close')}
                    onClick={() => setPreviewFullscreen(false)}
                  >
                    <X size={20} />
                  </button>
                  {previewCombined ? (
                    <img
                      className="tagging-preview__fullscreen-image"
                      src={previewImages[0].data_url}
                      alt=""
                      width={previewImages[0].width}
                      height={previewImages[0].height}
                    />
                  ) : (
                    <div className="tagging-preview__fullscreen-frames">
                      {previewImages.map((image, index) => (
                        <img
                          key={index}
                          className="tagging-preview__fullscreen-image"
                          src={image.data_url}
                          alt=""
                          width={image.width}
                          height={image.height}
                        />
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </section>
  )
}
