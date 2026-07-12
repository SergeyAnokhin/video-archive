import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Tag as TagIcon, X } from 'lucide-react'
import { getRecentTags, recordRecentTag } from '../utils/recentTags'
import type { Tag } from '../types/api'
import './QuickTagAdd.css'

interface QuickTagAddProps {
  fileId: string
  onTagAdded?: () => void
}

// Compact inline tag-add control meant to sit directly over the playback
// screen's video (user request): no modal, a transparent input that toggles
// open/closed, suggesting the 5 most recently used tags when empty and, once
// typing starts, the 5 best-matching tags actually assigned somewhere in
// this archive (not the full Settings vocabulary -- see
// `GET /api/tags/used`).
export function QuickTagAdd({ fileId, onTagAdded }: QuickTagAddProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState('')
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    if (!open) {
      return
    }
    const query = value.trim()
    if (!query) {
      setSuggestions(getRecentTags())
      return
    }
    let cancelled = false
    const timer = setTimeout(() => {
      void (async () => {
        try {
          const res = await fetch(`/api/tags/used?query=${encodeURIComponent(query)}&limit=5`)
          if (!res.ok) {
            throw new Error(`HTTP ${res.status}`)
          }
          const data: { tags: Tag[] } = await res.json()
          if (!cancelled) {
            setSuggestions(data.tags.map((tag) => tag.display_name))
          }
        } catch {
          if (!cancelled) {
            setSuggestions([])
          }
        }
      })()
    }, 250)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [open, value])

  async function handleAdd(displayName: string) {
    const trimmed = displayName.trim()
    if (!trimmed || adding) {
      return
    }
    setAdding(true)
    setError(null)
    try {
      const res = await fetch(`/api/files/${fileId}/tags`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: trimmed }),
      })
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`)
      }
      recordRecentTag(trimmed)
      setValue('')
      setSuggestions(getRecentTags())
      onTagAdded?.()
      inputRef.current?.focus()
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
    setOpen((current) => {
      const next = !current
      if (next) {
        setValue('')
        setSuggestions(getRecentTags())
        setError(null)
      }
      return next
    })
  }

  return (
    <div className="quick-tag-add" onClick={(event) => event.stopPropagation()}>
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
              {suggestions.map((name) => (
                <button
                  key={name}
                  type="button"
                  className="quick-tag-add__suggestion"
                  disabled={adding}
                  onClick={() => void handleAdd(name)}
                >
                  {name}
                </button>
              ))}
            </div>
          )}
          {error && <p className="quick-tag-add__error">{error}</p>}
        </form>
      )}
      <button
        type="button"
        className="quick-tag-add__toggle"
        aria-label={t('library.tagsAddButton')}
        title={t('library.tagsAddButton')}
        onClick={toggleOpen}
      >
        {open ? <X size={16} /> : <TagIcon size={16} />}
      </button>
    </div>
  )
}
