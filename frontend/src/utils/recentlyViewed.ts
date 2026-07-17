import { api } from '../api/client'
import type { FileEntry } from '../types/api'

const STORAGE_KEY = 'video-archive:recently-viewed'
const MAX_ENTRIES = 3

export function recordRecentlyViewed(fileId: string) {
  const next = [fileId, ...getRecentlyViewedIds().filter((id) => id !== fileId)].slice(0, MAX_ENTRIES)
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
}

export function getRecentlyViewedIds(): string[] {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? '[]')
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === 'string') : []
  } catch {
    return []
  }
}

// Sample file ids for the Settings preview-style live preview (up to 3): the
// most recently played videos, or -- before anything has been played yet --
// the first few video files with a ready preview anywhere in the connected
// source, so there's always something to show the effect on.
export async function loadPreviewSampleFileIds(): Promise<string[]> {
  const recent = getRecentlyViewedIds()
  if (recent.length > 0) return recent.slice(0, MAX_ENTRIES)

  try {
    const data = await api<{ files: FileEntry[] }>('/api/files?video_only=true&limit=20')
    return data.files
      .filter((file) => file.has_preview_asset)
      .slice(0, MAX_ENTRIES)
      .map((file) => file.id)
  } catch {
    return []
  }
}
