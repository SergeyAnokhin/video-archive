// Preview assets are regenerated in place under a fixed URL, so the
// generation timestamp is appended as a version: the backend lets the
// browser cache a versioned URL indefinitely, and once a reloaded listing
// reports a new timestamp, <img> fetches the new asset instead.
//
// A manual refresh (the folder toolbar's refresh button, the info panel's
// file refresh) additionally stamps a per-browser refresh token onto the
// affected URLs, for an asset that changed on disk without a new timestamp.
// It lives in localStorage because the browser cache it works around is
// per-browser too, and must survive a page reload.

const STORAGE_KEY = 'video-archive:preview-refresh-tokens'
const MAX_ENTRIES = 2000

let tokens: Record<string, string> | null = null

function loadTokens(): Record<string, string> {
  if (tokens === null) {
    try {
      const parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? '{}')
      tokens = parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
    } catch {
      tokens = {}
    }
  }
  return tokens!
}

function fileKey(fileId: string): string {
  return `f:${fileId}`
}

function folderKey(path: string): string {
  return `d:${path}`
}

// Forces the browser to re-fetch these files' collages/GIFs and these
// folders' GIFs on their next render.
export function refreshPreviewCache(target: { fileIds?: string[]; folderPaths?: string[] }) {
  const current = loadTokens()
  const token = Date.now().toString(36)
  const keys = [...(target.fileIds ?? []).map(fileKey), ...(target.folderPaths ?? []).map(folderKey)]
  for (const key of keys) {
    // Re-insert so the key moves to the end: the oldest entries are dropped first.
    delete current[key]
    current[key] = token
  }
  const entries = Object.entries(current)
  tokens = Object.fromEntries(entries.slice(Math.max(0, entries.length - MAX_ENTRIES)))
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(tokens))
  } catch {
    // Storage unavailable: the refresh still applies for this page session.
  }
}

function withVersion(url: string, generatedAt: string | null | undefined, refreshKey: string): string {
  const params = new URLSearchParams()
  if (generatedAt) {
    params.set('v', generatedAt)
  }
  const token = loadTokens()[refreshKey]
  if (token) {
    params.set('r', token)
  }
  const query = params.toString()
  if (!query) {
    return url
  }
  return `${url}${url.includes('?') ? '&' : '?'}${query}`
}

export function fileCollageUrl(file: { id: string; preview_generated_at?: string | null }): string {
  return withVersion(`/api/files/${file.id}/preview.jpg`, file.preview_generated_at, fileKey(file.id))
}

export function fileGifUrl(file: { id: string; preview_generated_at?: string | null }): string {
  return withVersion(`/api/files/${file.id}/preview.gif`, file.preview_generated_at, fileKey(file.id))
}

export function folderGifUrl(dir: { path: string; folder_preview_generated_at?: string | null }): string {
  return withVersion(
    `/api/directories/preview.gif?path=${encodeURIComponent(dir.path)}`,
    dir.folder_preview_generated_at,
    folderKey(dir.path),
  )
}
