import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Tag as TagIcon, X } from 'lucide-react'
import { getRecentTags, recordRecentTag } from '../utils/recentTags'
import { buildTagSuggestions } from '../utils/tagSuggestions'
import { api } from '../api/client'
import type { Tag } from '../types/api'
import { TagBadge } from './TagBadge'
import './QuickTagAdd.css'

interface QuickTagAddProps {
  fileId: string
  onTagAdded?: () => void
  // Controlled open state (user report: opening this while UserDefinedTagButton
  // was already open left both popovers stacked on screen at once). Optional
  // -- omitted, this falls back to managing its own open/closed state, so a
  // caller that doesn't need cross-popover coordination doesn't have to wire
  // anything up.
  open?: boolean
  onOpenChange?: (open: boolean) => void
}

// Compact inline tag-add control meant to sit directly over the playback
// screen's video (user request): no modal, a transparent input that toggles
// open/closed. Suggestions (user request) put the 10 tags most recently
// added manually through a "+"-style control first (`recentTags.ts`, shared
// across QuickTagAdd/FileInfoPanel/TagLabModal), then up to 10 more of the
// best-matching tags actually assigned somewhere in this archive (not the
// full Settings vocabulary -- see `GET /api/tags/used`), each rendered as
// its own colored `TagBadge` (user request -- every tag has one color shown
// identically everywhere, and this suggestion list was a plain-text
// exception to that).
export function QuickTagAdd({ fileId, onTagAdded, open: controlledOpen, onOpenChange }: QuickTagAddProps) {
  const { t } = useTranslation()
  const [uncontrolledOpen, setUncontrolledOpen] = useState(false)
  const open = controlledOpen ?? uncontrolledOpen
  function setOpen(next: boolean) {
    if (controlledOpen === undefined) {
      setUncontrolledOpen(next)
    }
    onOpenChange?.(next)
  }
  const [value, setValue] = useState('')
  const [suggestions, setSuggestions] = useState<Tag[]>([])
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Brief "just picked this" pulse on the clicked suggestion (user report --
  // this popover stays open to add more tags in a row, but a click on a
  // suggestion gave no sign it had registered at all before the list
  // possibly reshuffled; see TagBadge.tsx's `confirmed` prop).
  const [confirmedId, setConfirmedId] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    if (!open) {
      return
    }
    let cancelled = false
    const timer = setTimeout(() => {
      void (async () => {
        try {
          const query = value.trim()
          const data = await api<{ tags: Tag[] }>(`/api/tags/used?${new URLSearchParams({ query, limit: '100' })}`)
          if (!cancelled) {
            setSuggestions(buildTagSuggestions(getRecentTags(), data.tags))
          }
        } catch {
          if (!cancelled) {
            setSuggestions([])
          }
        }
      })()
    }, value.trim() ? 250 : 0)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [open, value])

  // `confirmId` is the clicked suggestion's tag id (omitted for a free-typed
  // name, which has no badge to animate).
  async function handleAdd(displayName: string, confirmId?: string) {
    const trimmed = displayName.trim()
    if (!trimmed || adding) {
      return
    }
    setAdding(true)
    setError(null)
    try {
      await api(`/api/files/${fileId}/tags`, {
        method: 'POST',
        body: { display_name: trimmed },
      })
      recordRecentTag(trimmed)
      setValue('')
      onTagAdded?.()
      inputRef.current?.focus()
      if (confirmId) {
        setConfirmedId(confirmId)
        window.setTimeout(() => setConfirmedId(null), 350)
      }
    } catch {
      setError(t('library.tagsAddError'))
    } finally {
      setAdding(false)
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    void handleAdd(value)
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Escape') {
      event.stopPropagation()
      setOpen(false)
      setValue('')
    }
  }

  function toggleOpen() {
    const next = !open
    if (next) {
      setValue('')
      setError(null)
    }
    setOpen(next)
  }

  return (
    <div className="quick-tag-add" onClick={(event) => event.stopPropagation()}>
      <button
        type="button"
        className="quick-tag-add__toggle"
        aria-label={t('library.tagsAddButton')}
        title={t('library.tagsAddButton')}
        onClick={toggleOpen}
      >
        {open ? <X size={16} /> : <TagIcon size={16} />}
      </button>
      {open && (
        <form className="quick-tag-add__form" onSubmit={handleSubmit}>
          <input
            ref={inputRef}
            type="text"
            autoFocus
            className="quick-tag-add__input"
            placeholder={t('library.tagsAddPlaceholder')}
            value={value}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={handleKeyDown}
            disabled={adding}
          />
          {suggestions.length > 0 && (
            <div className="quick-tag-add__suggestions">
              {suggestions.map((tag) => (
                <TagBadge
                  key={tag.id}
                  displayName={tag.display_name}
                  color={tag.color}
                  confirmed={confirmedId === tag.id}
                  onClick={adding ? undefined : () => void handleAdd(tag.display_name, tag.id)}
                />
              ))}
            </div>
          )}
          {error && <p className="quick-tag-add__error">{error}</p>}
        </form>
      )}
    </div>
  )
}
