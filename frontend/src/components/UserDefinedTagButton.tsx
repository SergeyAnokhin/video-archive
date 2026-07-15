import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Sparkles, X } from 'lucide-react'
import type { Tag } from '../types/api'
import './QuickTagAdd.css'
import './UserDefinedTagButton.css'

interface UserDefinedTagButtonProps {
  fileId: string
  onTagAdded?: () => void
  // 'overlay' floats over the video/image (playback screen, reuses
  // QuickTagAdd's semi-transparent chrome); 'panel' sits inside an opaque
  // surface (FileInfoPanel).
  variant?: 'overlay' | 'panel'
}

// Dedicated picker for the user-defined tag pool (user request): distinct
// from the free-text add controls (`QuickTagAdd`, `FileInfoPanel`'s own
// add-tag form), which create ordinary ad-hoc tags in neither managed pool.
// Existing user-defined tags (Settings' own curated list) are offered as
// one-click picks; typing a new name creates (or promotes) one on the fly.
export function UserDefinedTagButton({ fileId, onTagAdded, variant = 'overlay' }: UserDefinedTagButtonProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState('')
  const [options, setOptions] = useState<Tag[]>([])
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    if (!open) {
      return
    }
    let cancelled = false
    fetch('/api/tags?category=user')
      .then((res) => (res.ok ? res.json() : null))
      .then((data: { tags: Tag[] } | null) => {
        if (!cancelled) {
          setOptions(data?.tags.filter((tag) => tag.is_active) ?? [])
        }
      })
    return () => {
      cancelled = true
    }
  }, [open])

  async function assign(body: { tag_id: string } | { display_name: string }) {
    if (adding) {
      return
    }
    setAdding(true)
    setError(null)
    try {
      const res = await fetch(`/api/files/${fileId}/tags/user-defined`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`)
      }
      setValue('')
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
    const trimmed = value.trim()
    if (trimmed) {
      void assign({ display_name: trimmed })
    }
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
        setError(null)
      }
      return next
    })
  }

  const toggleClass = variant === 'overlay' ? 'quick-tag-add__toggle' : 'user-defined-tag-button__toggle'
  const formClass = variant === 'overlay' ? 'quick-tag-add__form' : 'user-defined-tag-button__form'
  const inputClass = variant === 'overlay' ? 'quick-tag-add__input' : 'user-defined-tag-button__input'
  const suggestionsClass = variant === 'overlay' ? 'quick-tag-add__suggestions' : 'user-defined-tag-button__options'
  const suggestionClass = variant === 'overlay' ? 'quick-tag-add__suggestion' : 'user-defined-tag-button__option'
  const errorClass = variant === 'overlay' ? 'quick-tag-add__error' : 'user-defined-tag-button__error'

  return (
    <div className="user-defined-tag-button" onClick={(event) => event.stopPropagation()}>
      <button
        type="button"
        className={toggleClass}
        aria-label={t('library.userDefinedTagButton')}
        title={t('library.userDefinedTagButton')}
        onClick={toggleOpen}
      >
        {open ? <X size={16} /> : <Sparkles size={16} />}
      </button>
      {open && (
        <form className={formClass} onSubmit={handleSubmit}>
          <input
            ref={inputRef}
            type="text"
            autoFocus
            className={inputClass}
            placeholder={t('library.userDefinedTagPlaceholder')}
            value={value}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={handleKeyDown}
            disabled={adding}
          />
          {options.length > 0 && (
            <div className={suggestionsClass}>
              {options.map((tag) => (
                <button
                  key={tag.id}
                  type="button"
                  className={suggestionClass}
                  disabled={adding}
                  onClick={() => void assign({ tag_id: tag.id })}
                >
                  {tag.display_name}
                </button>
              ))}
            </div>
          )}
          {error && <p className={errorClass}>{error}</p>}
        </form>
      )}
    </div>
  )
}
