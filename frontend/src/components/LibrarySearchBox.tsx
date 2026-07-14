import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { FileVideo, Folder, Search, Tag as TagIcon, X } from 'lucide-react'
import { useTags } from '../context/TagsContext'
import { useInterfaceSettings } from '../context/InterfaceSettingsContext'
import type { DirectoryEntry, DirectorySearchResponse, FileEntry, Tag } from '../types/api'
import {
  formatSearchQuery,
  parseSearchQuery,
  type ActiveSearch,
  type SearchScope,
} from '../utils/searchQuery'
import './LibrarySearchBox.css'

export type { ActiveSearch } from '../utils/searchQuery'

interface LibrarySearchBoxProps {
  activeSearch: ActiveSearch | null
  onSearch: (search: ActiveSearch) => void
  onClear: () => void
  onOpenDirectory: (path: string) => void
}

// Below this many characters no file/directory suggestion request is sent;
// tag suggestions stay client-side (the vocabulary is already loaded).
const MIN_SERVER_TERM = 2
const DEBOUNCE_MS = 250

export function LibrarySearchBox({ activeSearch, onSearch, onClear, onOpenDirectory }: LibrarySearchBoxProps) {
  const { t } = useTranslation()
  const { tags } = useTags()
  const { searchLimits } = useInterfaceSettings()
  const [value, setValue] = useState('')
  const [open, setOpen] = useState(false)
  const [fileMatches, setFileMatches] = useState<FileEntry[]>([])
  const [dirMatches, setDirMatches] = useState<DirectoryEntry[]>([])
  const containerRef = useRef<HTMLDivElement | null>(null)

  // The active search can change from outside the box (the results view's
  // "search only in this group" buttons, the clear button on the results
  // banner) -- keep the input text in sync with it.
  useEffect(() => {
    setValue(activeSearch ? formatSearchQuery(activeSearch.scope, activeSearch.value) : '')
  }, [activeSearch])

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const { scope, term } = parseSearchQuery(value)
  const lowerTerm = term.toLowerCase()

  const tagMatches: Tag[] =
    (scope === 'all' || scope === 'tag') && lowerTerm
      ? tags
          .filter(
            (tag) => tag.tag_key.includes(lowerTerm) || tag.display_name.toLowerCase().includes(lowerTerm),
          )
          .slice(0, searchLimits.tags)
      : []

  // File/directory suggestions come from the backend ("contains" match),
  // debounced so typing doesn't fire a request per keystroke.
  useEffect(() => {
    const wantFiles = (scope === 'all' || scope === 'file') && term.length >= MIN_SERVER_TERM
    const wantDirs = (scope === 'all' || scope === 'path') && term.length >= MIN_SERVER_TERM
    if (!wantFiles) setFileMatches([])
    if (!wantDirs) setDirMatches([])
    if (!wantFiles && !wantDirs) return

    let cancelled = false
    const timer = window.setTimeout(async () => {
      try {
        if (wantFiles) {
          const params = new URLSearchParams({
            search: term,
            limit: String(searchLimits.files),
          })
          const res = await fetch(`/api/files?${params.toString()}`)
          const json: { files: FileEntry[] } = await res.json()
          if (!cancelled) setFileMatches(res.ok ? json.files : [])
        }
        if (wantDirs) {
          const params = new URLSearchParams({ q: term, limit: String(searchLimits.dirs) })
          const res = await fetch(`/api/directories/search?${params.toString()}`)
          const json: DirectorySearchResponse = await res.json()
          if (!cancelled) setDirMatches(res.ok ? json.directories : [])
        }
      } catch {
        // suggestions are best-effort; the search itself still works on Enter
      }
    }, DEBOUNCE_MS)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [scope, term, searchLimits.files, searchLimits.dirs])

  function submit(nextScope: SearchScope, nextTerm: string) {
    if (!nextTerm) {
      return
    }
    setOpen(false)
    setValue(formatSearchQuery(nextScope, nextTerm))
    onSearch({ scope: nextScope, label: formatSearchQuery(nextScope, nextTerm), value: nextTerm })
  }

  function openDirectory(dir: DirectoryEntry) {
    setOpen(false)
    setValue('')
    onClear()
    onOpenDirectory(dir.path)
  }

  function clear() {
    setValue('')
    setOpen(false)
    onClear()
  }

  const hasSuggestions = tagMatches.length > 0 || fileMatches.length > 0 || dirMatches.length > 0

  const narrowLabel = t('library.searchNarrow')

  function groupHeader(icon: ReactNode, labelKey: string, narrowScope: Exclude<SearchScope, 'all'>) {
    return (
      <div className="library-search__group-header">
        {icon}
        <span>{t(labelKey)}</span>
        {scope === 'all' && (
          <button
            type="button"
            className="library-search__narrow"
            title={narrowLabel}
            onClick={() => submit(narrowScope, term)}
          >
            {formatSearchQuery(narrowScope, '')}
          </button>
        )}
      </div>
    )
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
            submit(scope, term)
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
      {open && hasSuggestions && (
        <div className="library-search__suggestions">
          {tagMatches.length > 0 && (
            <div className="library-search__group">
              {groupHeader(<TagIcon size={12} />, 'library.searchGroupTags', 'tag')}
              <ul>
                {tagMatches.map((tag) => (
                  <li key={tag.id}>
                    <button type="button" onClick={() => submit('tag', tag.tag_key)}>
                      <TagIcon size={12} /> {tag.display_name}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {fileMatches.length > 0 && (
            <div className="library-search__group">
              {groupHeader(<FileVideo size={12} />, 'library.searchGroupFiles', 'file')}
              <ul>
                {fileMatches.map((file) => (
                  <li key={file.id}>
                    <button type="button" onClick={() => submit('file', file.file_name)}>
                      <FileVideo size={12} /> {file.file_name}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {dirMatches.length > 0 && (
            <div className="library-search__group">
              {groupHeader(<Folder size={12} />, 'library.searchGroupDirs', 'path')}
              <ul>
                {dirMatches.map((dir) => (
                  <li key={dir.path}>
                    <button type="button" onClick={() => openDirectory(dir)}>
                      <Folder size={12} />
                      <span className="library-search__dir-name">{dir.name}</span>
                      <span className="library-search__dir-path">{dir.path}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
