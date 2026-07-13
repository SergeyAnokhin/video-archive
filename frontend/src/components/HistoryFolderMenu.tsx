import { Folder } from 'lucide-react'
import './HistoryFolderMenu.css'

interface HistoryFolderMenuProps {
  paths: string[]
  rootLabel: string
  onSelect: (path: string) => void
}

// Dropdown list of recently visited/used folders, shared by the library
// toolbar (folder navigation history) and FolderQuickActions (move-to-recent-
// folder history) so both look and behave identically: one folder per row, no
// wrapping, and each path segment clickable to jump to that segment.
export function HistoryFolderMenu({ paths, rootLabel, onSelect }: HistoryFolderMenuProps) {
  return (
    <div className="history-folder-menu" role="menu">
      {paths.map((path, index) => {
        const segments = path ? path.split('/') : [rootLabel]
        return (
          <div key={`${path}-${index}`} className="history-folder-menu__item">
            <Folder size={14} className="history-folder-menu__icon" />
            <span className="history-folder-menu__path">
              {segments.map((segment, segmentIndex) => {
                const isLast = segmentIndex === segments.length - 1
                const targetPath = path ? segments.slice(0, segmentIndex + 1).join('/') : ''
                return (
                  <span key={segmentIndex} className="history-folder-menu__segment-wrap">
                    <button
                      type="button"
                      className={`history-folder-menu__segment${isLast ? ' history-folder-menu__segment--current' : ''}`}
                      onClick={() => onSelect(targetPath)}
                    >
                      {segment}
                    </button>
                    {!isLast && <span className="history-folder-menu__sep">/</span>}
                  </span>
                )
              })}
            </span>
          </div>
        )
      })}
    </div>
  )
}
