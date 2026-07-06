import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronRight, Folder } from 'lucide-react'
import { useSource } from '../context/SourceContext'
import type { TreeNode } from '../types/api'
import './DirectoryTree.css'

interface DirectoryTreeProps {
  selectedPath: string
  onSelect: (path: string) => void
}

export function DirectoryTree({ selectedPath, onSelect }: DirectoryTreeProps) {
  const { t } = useTranslation()
  const { source } = useSource()
  const [root, setRoot] = useState<TreeNode | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setRoot(null)
    setError(null)

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

  if (error) {
    return (
      <p className="app-nav__placeholder">{t('sidebar.treeError', { message: error })}</p>
    )
  }

  if (!root) {
    return <p className="app-nav__placeholder">{t('sidebar.loading')}</p>
  }

  return (
    <div className="directory-tree">
      <TreeEntry node={root} depth={0} selectedPath={selectedPath} onSelect={onSelect} isRoot />
    </div>
  )
}

interface TreeEntryProps {
  node: TreeNode
  depth: number
  selectedPath: string
  onSelect: (path: string) => void
  isRoot?: boolean
}

function TreeEntry({ node, depth, selectedPath, onSelect, isRoot = false }: TreeEntryProps) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(true)
  const hasChildren = node.children.length > 0
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
            onClick={() => setExpanded((value) => !value)}
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
          <span>{isRoot ? node.name : node.name}</span>
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
            />
          ))}
        </div>
      )}
    </div>
  )
}
