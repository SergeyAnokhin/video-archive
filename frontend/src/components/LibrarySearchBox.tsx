import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Search, Tag as TagIcon, X } from 'lucide-react'
import { useTags } from '../context/TagsContext'
import type { Tag } from '../types/api'
import './LibrarySearchBox.css'

export interface ActiveSearch {
  kind: 'tag' | 'name'
  label: string
  value: string
}

interface LibrarySearchBoxProps {
  onSearch: (search: ActiveSearch) => void
  onClear: () => void
}

export function LibrarySearchBox({ onSearch, onClear }: LibrarySearchBoxProps) {
  const { t } = useTranslation()
  const { tags } = useTags()
  const [value, setValue] = useState('')
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const prefix = value.trim().toLowerCase()
  const suggestions: Tag[] = prefix
    ? tags.filter((tag) => tag.tag_key.startsWith(prefix)).slice(0, 8)
    : []

  function selectTag(tag: Tag) {
    setValue(tag.display_name)
    setOpen(false)
    onSearch({ kind: 'tag', label: tag.display_name, value: tag.tag_key })
  }

  function submitFreeText() {
    if (!value.trim()) {
      return
    }
    setOpen(false)
    onSearch({ kind: 'name', label: value.trim(), value: value.trim() })
  }

  function clear() {
    setValue('')
    setOpen(false)
    onClear()
  }

  return (
    <div className="library-search" ref={containerRef}>
      <Search size={14} className="library-search__icon" />
      <input
        type="text"
        className="library-search__input"
        placeholder={t('library.searchPlaceholder')}
        value={value}
        onChange={(event) => {
          setValue(event.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            submitFreeText()
          } else if (event.key === 'Escape') {
            setOpen(false)
          }
        }}
      />
      {value && (
        <button
          type="button"
          className="library-search__clear"
          aria-label={t('library.searchClear')}
          onClick={clear}
        >
          <X size={12} />
        </button>
      )}
      {open && suggestions.length > 0 && (
        <ul className="library-search__suggestions">
          {suggestions.map((tag) => (
            <li key={tag.id}>
              <button type="button" onClick={() => selectTag(tag)}>
                <TagIcon size={12} /> {tag.display_name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
