import { beforeEach, describe, expect, it, vi } from 'vitest'

// Same in-memory localStorage stub as recentFolders.test.ts (no jsdom here).
class FakeStorage {
  private store = new Map<string, string>()
  getItem(key: string) {
    return this.store.has(key) ? this.store.get(key)! : null
  }
  setItem(key: string, value: string) {
    this.store.set(key, value)
  }
  clear() {
    this.store.clear()
  }
}

;(globalThis as unknown as { window: { localStorage: FakeStorage } }).window = { localStorage: new FakeStorage() }

// The module caches the parsed tokens, so each test gets a fresh copy of it.
async function load() {
  vi.resetModules()
  return import('./previewUrl')
}

beforeEach(() => {
  window.localStorage.clear()
})

describe('preview URLs', () => {
  it('leaves an unversioned URL untouched', async () => {
    const { fileCollageUrl, folderGifUrl } = await load()
    expect(fileCollageUrl({ id: 'a' })).toBe('/api/files/a/preview.jpg')
    expect(folderGifUrl({ path: 'x y' })).toBe('/api/directories/preview.gif?path=x%20y')
  })

  it('versions URLs by generation timestamp', async () => {
    const { fileGifUrl, folderGifUrl } = await load()
    expect(fileGifUrl({ id: 'a', preview_generated_at: '2026-01-01T00:00:00+00:00' })).toBe(
      '/api/files/a/preview.gif?v=2026-01-01T00%3A00%3A00%2B00%3A00',
    )
    expect(folderGifUrl({ path: 'x', folder_preview_generated_at: 't1' })).toBe(
      '/api/directories/preview.gif?path=x&v=t1',
    )
  })

  it('adds a refresh token only to the refreshed files and folders, and keeps it across reloads', async () => {
    vi.spyOn(Date, 'now').mockReturnValue(36 ** 3)
    const first = await load()
    first.refreshPreviewCache({ fileIds: ['a'], folderPaths: ['x'] })

    const { fileCollageUrl, folderGifUrl } = await load()
    expect(fileCollageUrl({ id: 'a', preview_generated_at: 't1' })).toBe('/api/files/a/preview.jpg?v=t1&r=1000')
    expect(fileCollageUrl({ id: 'b', preview_generated_at: 't1' })).toBe('/api/files/b/preview.jpg?v=t1')
    expect(folderGifUrl({ path: 'x' })).toBe('/api/directories/preview.gif?path=x&r=1000')
    vi.restoreAllMocks()
  })

  it('drops the oldest tokens past the cap', async () => {
    const { refreshPreviewCache } = await load()
    refreshPreviewCache({ fileIds: Array.from({ length: 2001 }, (_, i) => `f${i}`) })
    const stored = JSON.parse(window.localStorage.getItem('video-archive:preview-refresh-tokens')!)
    expect(Object.keys(stored)).toHaveLength(2000)
    expect(stored['f:f0']).toBeUndefined()
    expect(stored['f:f2000']).toBeDefined()
  })
})
