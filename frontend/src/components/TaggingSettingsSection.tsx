import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useTags } from '../context/TagsContext'
import type { ProviderName, Tag, TaggingSettings } from '../types/api'

const PROVIDERS: ProviderName[] = ['openrouter', 'gemini', 'fal', 'mistral']

export function TaggingSettingsSection() {
  const { t } = useTranslation()
  const { tags, refresh: refreshTags } = useTags()
  const [settings, setSettings] = useState<TaggingSettings | null>(null)
  const [newTagName, setNewTagName] = useState('')
  const [tagError, setTagError] = useState<string | null>(null)
  const [savingSettings, setSavingSettings] = useState(false)

  useEffect(() => {
    void (async () => {
      const res = await fetch('/api/tagging-settings')
      if (res.ok) {
        setSettings(await res.json())
      }
    })()
  }, [])

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
    setSavingSettings(true)
    try {
      const res = await fetch('/api/tagging-settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(next),
      })
      if (res.ok) {
        setSettings(await res.json())
      }
    } finally {
      setSavingSettings(false)
    }
  }

  return (
    <section className="settings-modal__section">
      <h3 className="settings-modal__section-title">{t('tagging.title')}</h3>

      <p className="settings-modal__hint">{t('tagging.vocabularyHint')}</p>

      {tags.length === 0 && <p className="settings-modal__hint">{t('tagging.vocabularyEmpty')}</p>}

      {tags.map((tag) => (
        <div key={tag.id} className="conversion-profile-row">
          <div>
            <input
              className="settings-modal__input"
              defaultValue={tag.display_name}
              onBlur={(event) => void handleRenameTag(tag, event.target.value)}
            />
          </div>
          <div className="settings-modal__actions">
            <button type="button" className="settings-modal__option" onClick={() => void handleToggleActive(tag)}>
              {tag.is_active ? t('tagging.deactivate') : t('tagging.activate')}
            </button>
            <button type="button" className="settings-modal__option" onClick={() => void handleDeleteTag(tag)}>
              {t('tagging.delete')}
            </button>
          </div>
        </div>
      ))}

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
        <button type="button" className="settings-modal__option" onClick={() => void handleAddTag()}>
          {t('tagging.add')}
        </button>
      </div>
      {tagError && <p className="settings-modal__hint settings-modal__hint--error">{tagError}</p>}

      {settings && (
        <>
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
            {t('tagging.defaultProvider')}
            <select
              className="settings-modal__input"
              value={settings.default_provider ?? ''}
              onChange={(event) => {
                const next = { ...settings, default_provider: event.target.value || null }
                setSettings(next)
                void handleSaveSettings(next)
              }}
            >
              <option value="">{t('tagging.noDefaultProvider')}</option>
              {PROVIDERS.map((provider) => (
                <option key={provider} value={provider}>
                  {t(`providers.${provider}`)}
                </option>
              ))}
            </select>
          </label>

          <label className="settings-modal__label">
            {t('tagging.defaultVisionModel')}
            <input
              className="settings-modal__input"
              value={settings.default_vision_model ?? ''}
              onChange={(event) => setSettings({ ...settings, default_vision_model: event.target.value || null })}
              onBlur={() => void handleSaveSettings(settings)}
              disabled={savingSettings}
            />
          </label>
        </>
      )}
    </section>
  )
}
