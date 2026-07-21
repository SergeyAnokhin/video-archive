import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, Folder, Search } from 'lucide-react'
import { tryApi } from '../api/client'
import type { DirectoryEntry } from '../types/api'
import './BreadcrumbSwitcher.css'

interface BreadcrumbSwitcherProps {
  parentPath: string
  currentPath: string
  onSelect: (path: string) => void
}

// Small chevron next to each breadcrumb segment (GitHub repo-switcher style):
// opens a compact popover listing the segment's siblings (children of its
// parent) so switching sideways -- e.g. 2024.01 -> 2024.02 -- takes one
// click instead of navigating up then back down (user request).
export function BreadcrumbSwitcher({ parentPath, currentPath, onSelect }: BreadcrumbSwitcherProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [directories, setDirectories] = useState<DirectoryEntry[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [filterText, setFilterText] = useState('')
  const containerRef = useRef<HTMLSpanElement | null>(null)

  useEffect(() => {
    if (!open) {
      return
    }
    let cancelled = false
    setLoading(true)
    tryApi<{ directories: DirectoryEntry[] }>(`/api/directories/children?path=${encodeURIComponent(parentPath)}`)
      .then((json) => {
        if (!cancelled) {
          setDirectories(json?.directories ?? [])
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [open, parentPath])

  useEffect(() => {
    if (!open) {
      return
    }
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open])

  function handleToggle() {
    setOpen((current) => !current)
    if (open) {
      setFilterText('')
      setDirectories(null)
    }
  }

  function handleSelect(path: string) {
    setOpen(false)
    setFilterText('')
    onSelect(path)
  }

  const filterQuery = filterText.trim().toLowerCase()
  const filtered = directories?.filter((dir) => dir.name.toLowerCase().includes(filterQuery)) ?? null

  return (
    <span className="breadcrumb-switcher" ref={containerRef}>
      <button
        type="button"
        className="breadcrumb-switcher__toggle"
        aria-label={t('library.breadcrumbSwitchLabel')}
        title={t('library.breadcrumbSwitchLabel')}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={handleToggle}
      >
        <ChevronDown size={12} />
      </button>

      {open && (
        <div className="breadcrumb-switcher__menu" role="menu" onClick={(event) => event.stopPropagation()}>
          <div className="breadcrumb-switcher__filter">
            <Search size={12} className="breadcrumb-switcher__filter-icon" />
            <input
              type="text"
              className="breadcrumb-switcher__filter-input"
              placeholder={t('library.breadcrumbSwitchSearchPlaceholder')}
              value={filterText}
              onChange={(event) => setFilterText(event.target.value)}
              autoFocus
            />
          </div>

          {loading && <p className="breadcrumb-switcher__hint">{t('library.loading')}</p>}

          {!loading && filtered && filtered.length === 0 && (
            <p className="breadcrumb-switcher__hint">
              {directories && directories.length === 0
                ? t('library.breadcrumbSwitchEmpty')
                : t('library.breadcrumbSwitchNoMatches')}
            </p>
          )}

          {!loading && filtered && filtered.length > 0 && (
            <div className="breadcrumb-switcher__list">
              {filtered.map((dir) => (
                <button
                  key={dir.path}
                  type="button"
                  className={`breadcrumb-switcher__item${dir.path === currentPath ? ' breadcrumb-switcher__item--current' : ''}`}
                  onClick={() => handleSelect(dir.path)}
                >
                  <Folder size={13} />
                  <span>{dir.name}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </span>
  )
}
