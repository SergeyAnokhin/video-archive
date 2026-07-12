const STORAGE_KEY = 'video-archive:recent-tags'
const MAX_ENTRIES = 5

// De-duped most-recent-first list (like recentlyViewed.ts) of tag display
// names entered through the playback screen's quick tag-add control (user
// request) -- feeds its empty-input suggestion list.
export function recordRecentTag(displayName: string) {
  const trimmed = displayName.trim()
  if (!trimmed) {
    return
  }
  const key = trimmed.toLowerCase()
  const next = [trimmed, ...getRecentTags().filter((tag) => tag.toLowerCase() !== key)].slice(0, MAX_ENTRIES)
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
}

export function getRecentTags(): string[] {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? '[]')
    return Array.isArray(parsed) ? parsed.filter((tag): tag is string => typeof tag === 'string') : []
  } catch {
    return []
  }
}
