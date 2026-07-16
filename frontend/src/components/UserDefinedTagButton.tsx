import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Sparkles, X } from 'lucide-react'
import type { Tag } from '../types/api'
import { TagBadge } from './TagBadge'
import './QuickTagAdd.css'
import './UserDefinedTagButton.css'

interface UserDefinedTagButtonProps {
  fileId: string
  onTagAdded?: () => void
  // 'overlay' floats over the video/image (playback screen, reuses
  // QuickTagAdd's semi-transparent chrome); 'panel' sits inside an opaque
  // surface (FileInfoPanel).
  variant?: 'overlay' | 'panel'
  // Controlled open state (user report: opening this while QuickTagAdd was
  // already open left both popovers stacked on screen at once). Optional --
  // omitted, this falls back to managing its own open/closed state (e.g.
  // FileInfoPanel's standalone `variant="panel"` usage, which has no sibling
  // picker to coordinate with).
  open?: boolean
  onOpenChange?: (open: boolean) => void
}

// Dedicated picker for the user-defined tag pool (user request): distinct
// from the free-text add controls (`QuickTagAdd`, `FileInfoPanel`'s own
// add-tag form), which create ordinary ad-hoc tags in neither managed pool.
// Existing user-defined tags (Settings' own curated list) are offered as
// one-click picks; typing a new name creates (or promotes) one on the fly.
export function UserDefinedTagButton({
  fileId,
  onTagAdded,
  variant = 'overlay',
  open: controlledOpen,
  onOpenChange,
}: UserDefinedTagButtonProps) {
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
  const [options, setOptions] = useState<Tag[]>([])
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Brief "just picked this" pulse on the clicked badge before the popover
  // closes (user report -- picking a tag gave no feedback that the click
  // had registered at all, see TagBadge.tsx's `confirmed` prop).
  const [confirmedId, setConfirmedId] = useState<string | null>(null)
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

  // `confirmId` is the clicked badge's tag id (omitted for a free-typed
  // name, which has no badge to animate) -- shows the pop+checkmark on it
  // for a beat before the popover actually closes, so picking a tag reads
  // as "yes, that one" rather than the panel just vanishing.
  async function assign(body: { tag_id: string } | { display_name: string }, confirmId?: string) {
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
      if (confirmId) {
        setConfirmedId(confirmId)
        window.setTimeout(() => {
          setConfirmedId(null)
          setOpen(false)
        }, 350)
      } else {
        setOpen(false)
      }
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
    const next = !open
    if (next) {
      setValue('')
      setError(null)
    }
    setOpen(next)
  }

  const toggleClass = variant === 'overlay' ? 'quick-tag-add__toggle' : 'user-defined-tag-button__toggle'
  const formClass = variant === 'overlay' ? 'quick-tag-add__form' : 'user-defined-tag-button__form'
  const inputClass = variant === 'overlay' ? 'quick-tag-add__input' : 'user-defined-tag-button__input'
  const suggestionsClass = variant === 'overlay' ? 'quick-tag-add__suggestions' : 'user-defined-tag-button__options'
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
                <TagBadge
                  key={tag.id}
                  displayName={tag.display_name}
                  color={tag.color}
                  confirmed={confirmedId === tag.id}
                  onClick={adding ? undefined : () => void assign({ tag_id: tag.id }, tag.id)}
                />
              ))}
            </div>
          )}
          {error && <p className={errorClass}>{error}</p>}
        </form>
      )}
    </div>
  )
}
