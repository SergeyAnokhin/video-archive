import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronRight, ChevronsDownUp, ChevronsUpDown, Folder, Search, X } from 'lucide-react'
import { useSource } from '../context/SourceContext'
import type { TreeNode } from '../types/api'
import './DirectoryTree.css'

interface DirectoryTreeProps {
  selectedPath: string
  onSelect: (path: string) => void
}

// The tree's own root node stands in for the active source (its name is the
// source's name, see backend/app/routers/tree.py) rather than a real folder
// -- there's always exactly one active source, so showing it as a
// selectable row above the real top-level folders is just noise. We fetch
// and keep `root` for its .children, but never render a row for it.
function collectFilterPaths(node: TreeNode, query: string, into: Set<string>): boolean {
  let matched = node.name.toLowerCase().includes(query)
  for (const child of node.children) {
    if (collectFilterPaths(child, query, into)) {
      matched = true
    }
  }
  if (matched) {
    into.add(node.path)
  }
  return matched
}

function collectExpandablePaths(node: TreeNode, into: Set<string>) {
  if (node.children.length > 0) {
    into.add(node.path)
    for (const child of node.children) {
      collectExpandablePaths(child, into)
    }
  }
}

export function DirectoryTree({ selectedPath, onSelect }: DirectoryTreeProps) {
  const { t } = useTranslation()
  const { source } = useSource()
  const [root, setRoot] = useState<TreeNode | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [collapsedPaths, setCollapsedPaths] = useState<Set<string>>(new Set())
  const [filterText, setFilterText] = useState('')

  useEffect(() => {
    let cancelled = false
    setRoot(null)
    setError(null)
    setCollapsedPaths(new Set())
    setFilterText('')

    async function load() {
      try {
        const res = await fetch('/api/tree?include_status=true')
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`)
        }
        const data: TreeNode = await res.json()
        if (!cancelled) {
          setRoot(data)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err))
        }
      }
    }

    if (source) {
      void load()
    }

    return () => {
      cancelled = true
    }
  }, [source])

  const filterQuery = filterText.trim().toLowerCase()
  const filterPaths = useMemo(() => {
    if (!root || !filterQuery) {
      return null
    }
    const into = new Set<string>()
    for (const child of root.children) {
      collectFilterPaths(child, filterQuery, into)
    }
    return into
  }, [root, filterQuery])

  function handleToggle(path: string) {
    setCollapsedPaths((prev) => {
      const next = new Set(prev)
      if (next.has(path)) {
        next.delete(path)
      } else {
        next.add(path)
      }
      return next
    })
  }

  function handleExpandAll() {
    setCollapsedPaths(new Set())
  }

  function handleCollapseAll() {
    if (!root) {
      return
    }
    const all = new Set<string>()
    for (const child of root.children) {
      collectExpandablePaths(child, all)
    }
    setCollapsedPaths(all)
  }

  if (error) {
    return (
      <p className="app-nav__placeholder">{t('sidebar.treeError', { message: error })}</p>
    )
  }

  if (!root) {
    return <p className="app-nav__placeholder">{t('sidebar.loading')}</p>
  }

  const noMatches = filterPaths !== null && filterPaths.size === 0

  return (
    <div className="directory-tree">
      <div className="directory-tree__toolbar">
        <div className="directory-tree__filter">
          <Search size={14} className="directory-tree__filter-icon" />
          <input
            type="text"
            className="directory-tree__filter-input"
            placeholder={t('sidebar.filterPlaceholder')}
            value={filterText}
            onChange={(event) => setFilterText(event.target.value)}
          />
          {filterText && (
            <button
              type="button"
              className="directory-tree__filter-clear"
              aria-label={t('sidebar.clearFilter')}
              onClick={() => setFilterText('')}
            >
              <X size={12} />
            </button>
          )}
        </div>
        <div className="directory-tree__toolbar-actions">
          <button
            type="button"
            className="directory-tree__toolbar-btn"
            aria-label={t('sidebar.expandAll')}
            title={t('sidebar.expandAll')}
            onClick={handleExpandAll}
          >
            <ChevronsUpDown size={14} />
          </button>
          <button
            type="button"
            className="directory-tree__toolbar-btn"
            aria-label={t('sidebar.collapseAll')}
            title={t('sidebar.collapseAll')}
            onClick={handleCollapseAll}
          >
            <ChevronsDownUp size={14} />
          </button>
        </div>
      </div>

      {root.children.length === 0 ? (
        <p className="app-nav__placeholder">{t('sidebar.empty')}</p>
      ) : noMatches ? (
        <p className="app-nav__placeholder">{t('sidebar.noMatches')}</p>
      ) : (
        <div className="directory-tree__list">
          {root.children.map((child) => (
            <TreeEntry
              key={child.path}
              node={child}
              depth={0}
              selectedPath={selectedPath}
              onSelect={onSelect}
              collapsedPaths={collapsedPaths}
              onToggle={handleToggle}
              filterPaths={filterPaths}
            />
          ))}
        </div>
      )}
    </div>
  )
}

interface TreeEntryProps {
  node: TreeNode
  depth: number
  selectedPath: string
  onSelect: (path: string) => void
  collapsedPaths: Set<string>
  onToggle: (path: string) => void
  filterPaths: Set<string> | null
}

function TreeEntry({ node, depth, selectedPath, onSelect, collapsedPaths, onToggle, filterPaths }: TreeEntryProps) {
  const { t } = useTranslation()

  if (filterPaths && !filterPaths.has(node.path)) {
    return null
  }

  const hasChildren = node.children.length > 0
  // While filtering, every rendered node sits on the path to a match, so it
  // stays expanded regardless of manual collapse state (restored once the
  // filter is cleared).
  const expanded = filterPaths ? true : !collapsedPaths.has(node.path)
  const isSelected = node.path === selectedPath
  const status = node.status
  const showConversionDot = Boolean(status && !status.conversion_complete)
  const showPreviewDot = Boolean(status && !status.preview_complete)

  return (
    <div className="directory-tree__entry">
      <div
        className={`directory-tree__row${isSelected ? ' directory-tree__row--selected' : ''}`}
        style={{ paddingLeft: `${depth * 14}px` }}
      >
        {hasChildren ? (
          <button
            type="button"
            className={`directory-tree__toggle${expanded ? ' directory-tree__toggle--open' : ''}`}
            aria-label={t(expanded ? 'sidebar.collapse' : 'sidebar.expand')}
            onClick={() => onToggle(node.path)}
          >
            <ChevronRight size={14} />
          </button>
        ) : (
          <span className="directory-tree__toggle-spacer" />
        )}

        <button
          type="button"
          className="directory-tree__label"
          onClick={() => onSelect(node.path)}
        >
          <Folder size={14} />
          <span>{node.name}</span>
        </button>

        {showConversionDot && (
          <span
            className="directory-tree__dot directory-tree__dot--conversion"
            title={t('indicators.conversionIncomplete', {
              converted: status?.converted_count,
              total: status?.total_supported_files,
            })}
          />
        )}
        {showPreviewDot && (
          <span
            className="directory-tree__dot directory-tree__dot--preview"
            title={t('indicators.previewIncomplete', {
              generated: status?.preview_count,
              total: status?.total_supported_files,
            })}
          />
        )}
      </div>

      {expanded && hasChildren && (
        <div className="directory-tree__children">
          {node.children.map((child) => (
            <TreeEntry
              key={child.path}
              node={child}
              depth={depth + 1}
              selectedPath={selectedPath}
              onSelect={onSelect}
              collapsedPaths={collapsedPaths}
              onToggle={onToggle}
              filterPaths={filterPaths}
            />
          ))}
        </div>
      )}
    </div>
  )
}
