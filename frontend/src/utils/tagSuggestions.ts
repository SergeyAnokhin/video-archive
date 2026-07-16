import type { Tag } from '../types/api'

// Suggestion ordering shared by every "+"-style tag-add control (user
// request): tags the user has personally typed into one of these inputs
// before (`recentNames`, most-recent-first, see recentTags.ts) take priority
// over merely-popular ones. `pool` must already be filtered to whatever the
// caller is typing and ordered most-used-first (`GET /api/tags/used`'s own
// order, or a client-side filter over an already usage-ordered fetch) --
// this function only reorders/caps it, it never re-sorts by popularity
// itself.
export function buildTagSuggestions(recentNames: string[], pool: Tag[], perBlockLimit = 10): Tag[] {
  const byNameLower = new Map(pool.map((tag) => [tag.display_name.toLowerCase(), tag] as const))
  const seenIds = new Set<string>()
  const recent: Tag[] = []
  for (const name of recentNames) {
    const tag = byNameLower.get(name.trim().toLowerCase())
    if (tag && !seenIds.has(tag.id)) {
      recent.push(tag)
      seenIds.add(tag.id)
      if (recent.length >= perBlockLimit) {
        break
      }
    }
  }

  const popular: Tag[] = []
  for (const tag of pool) {
    if (popular.length >= perBlockLimit) {
      break
    }
    if (!seenIds.has(tag.id)) {
      popular.push(tag)
      seenIds.add(tag.id)
    }
  }

  return [...recent, ...popular]
}
