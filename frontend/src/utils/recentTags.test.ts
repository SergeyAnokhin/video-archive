import { beforeEach, describe, expect, it } from 'vitest'
import { getRecentTags, recordRecentTag } from './recentTags'

// Same in-memory localStorage stub as recentFolders.test.ts (no jsdom in
// this project's vitest setup for pure-function tests).
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

beforeEach(() => {
  window.localStorage.clear()
})

describe('recordRecentTag / getRecentTags', () => {
  it('starts empty', () => {
    expect(getRecentTags()).toEqual([])
  })

  it('prepends the most recently used tag', () => {
    recordRecentTag('Beach')
    recordRecentTag('Snow')
    expect(getRecentTags()).toEqual(['Snow', 'Beach'])
  })

  it('de-duplicates case-insensitively, keeping the newest casing first', () => {
    recordRecentTag('Beach')
    recordRecentTag('Snow')
    recordRecentTag('beach')
    expect(getRecentTags()).toEqual(['beach', 'Snow'])
  })

  it('ignores blank input', () => {
    recordRecentTag('  ')
    expect(getRecentTags()).toEqual([])
  })

  it('caps the list at 5 entries', () => {
    for (let i = 0; i < 8; i++) {
      recordRecentTag(`tag-${i}`)
    }
    const result = getRecentTags()
    expect(result).toHaveLength(5)
    expect(result[0]).toBe('tag-7')
  })
})
