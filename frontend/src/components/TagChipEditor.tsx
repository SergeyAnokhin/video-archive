import { Check, Copy, Plus } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { TagBadge } from './TagBadge'
import { api, tryApi } from '../api/client'
import type { Tag } from '../types/api'

interface TagChipEditorProps {
  tags: Tag[]
  onChanged: () => Promise<void>
  // Sent alongside `display_name` when creating a tag from this editor, so
  // e.g. the user-defined tags section creates `is_user_defined: true,
  // is_ai_vocabulary: false` instead of the create endpoint's own default
  // (AI vocabulary) -- reused as-is by `TaggingSettingsSection`'s own AI
  // vocabulary editor with an empty override (keeps the default).
  createDefaults?: Partial<Pick<Tag, 'is_ai_vocabulary' | 'is_user_defined'>>
  hintText: string
  emptyText: string
  placeholderText: string
}

export function TagChipEditor({
  tags,
  onChanged,
  createDefaults,
  hintText,
  emptyText,
  placeholderText,
}: TagChipEditorProps) {
  const { t } = useTranslation()
  const [newTagName, setNewTagName] = useState('')
  const [tagError, setTagError] = useState<string | null>(null)
  const [editingTagId, setEditingTagId] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const [copied, setCopied] = useState(false)

  async function handleAddTag() {
    if (!newTagName.trim()) {
      return
    }
    setTagError(null)
    try {
      await api('/api/tags', {
        method: 'POST',
        body: { display_name: newTagName.trim(), ...createDefaults },
      })
      setNewTagName('')
      await onChanged()
    } catch (err) {
      setTagError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleToggleActive(tag: Tag) {
    await tryApi(`/api/tags/${tag.id}`, {
      method: 'PUT',
      body: { ...tag, is_active: !tag.is_active },
    })
    await onChanged()
  }

  async function handleRenameTag(tag: Tag, displayName: string) {
    if (!displayName.trim() || displayName === tag.display_name) {
      return
    }
    await tryApi(`/api/tags/${tag.id}`, {
      method: 'PUT',
      body: { ...tag, display_name: displayName.trim() },
    })
    await onChanged()
  }

  async function handleSetColor(tag: Tag, color: string) {
    await tryApi(`/api/tags/${tag.id}`, {
      method: 'PUT',
      body: { ...tag, color },
    })
    await onChanged()
  }

  async function handleDeleteTag(tag: Tag) {
    await tryApi(`/api/tags/${tag.id}`, { method: 'DELETE' })
    await onChanged()
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
    <>
      <div className="tag-chip-toolbar">
        <p className="tag-chip-toolbar__hint">{hintText}</p>
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

      {tags.length === 0 && <p className="settings-modal__hint">{emptyText}</p>}

      <div className="tag-chip-list">
        {tags.map((tag) =>
          editingTagId === tag.id ? (
            <span key={tag.id} className="tag-chip tag-chip--editing">
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
            </span>
          ) : (
            <TagBadge
              key={tag.id}
              displayName={tag.display_name}
              color={tag.color}
              inactive={!tag.is_active}
              title={tag.is_active ? t('tagging.deactivate') : t('tagging.activate')}
              onClick={() => void handleToggleActive(tag)}
              onDoubleClick={() => startEditing(tag)}
              onColorChange={(color) => void handleSetColor(tag, color)}
              onRemove={() => void handleDeleteTag(tag)}
            />
          ),
        )}
      </div>

      <div className="settings-modal__actions">
        <input
          className="settings-modal__input"
          placeholder={placeholderText}
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
    </>
  )
}
