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
