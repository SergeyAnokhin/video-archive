const STORAGE_KEY = 'video-archive:recent-folders'
const MAX_ENTRIES = 10

// Unlike recentlyViewed.ts, this is a plain view log, not a deduped
// most-recent-first set: the same folder can appear more than once, just
// never twice in a row (opening several videos from the same folder
// shouldn't spam the history button with repeats).
export function recordRecentFolder(path: string) {
  const existing = getRecentFolders()
  if (existing[0] === path) {
    return
  }
  const next = [path, ...existing].slice(0, MAX_ENTRIES)
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
}

export function getRecentFolders(): string[] {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? '[]')
    return Array.isArray(parsed) ? parsed.filter((path): path is string => typeof path === 'string') : []
  } catch {
    return []
  }
}

const NAV_STORAGE_KEY = 'video-archive:folder-nav-history'
const NAV_MAX_ENTRIES = 10

// A separate, deduped most-recent-first list of folders navigated to in the
// library view (sidebar tree, breadcrumb, folder cards) -- powers the
// quick-jump "recent folders" button. Kept apart from
// recordRecentFolder/getRecentFolders above, which is a non-deduped view log
// used only by FolderQuickActions to move files into recently-viewed-from
// folders.
export function recordFolderVisit(path: string) {
  const next = [path, ...getRecentFolderVisits().filter((existing) => existing !== path)].slice(0, NAV_MAX_ENTRIES)
  window.localStorage.setItem(NAV_STORAGE_KEY, JSON.stringify(next))
}

export function getRecentFolderVisits(): string[] {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(NAV_STORAGE_KEY) ?? '[]')
    return Array.isArray(parsed) ? parsed.filter((path): path is string => typeof path === 'string') : []
  } catch {
    return []
  }
}
