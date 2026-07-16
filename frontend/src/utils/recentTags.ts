const STORAGE_KEY = 'video-archive:recent-tags'
const MAX_ENTRIES = 10

// De-duped most-recent-first list (like recentlyViewed.ts) of tag display
// names manually entered through any "+"-style tag-add control -- the
// playback screen's quick tag-add, FileInfoPanel's tag-add, and Tag Lab's
// add-more field (user request: these tags should surface first, ahead of
// merely-popular ones, in every such control's suggestion list -- see
// `buildTagSuggestions()` in tagSuggestions.ts).
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
