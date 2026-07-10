import { beforeEach, describe, expect, it } from 'vitest'
import { getRecentFolders, recordRecentFolder } from './recentFolders'

// No jsdom in this project's vitest setup (see format.test.ts/eta.test.ts --
// pure-function tests only): a minimal in-memory localStorage stub is enough
// to exercise this module's actual read/write logic without adding a
// browser-DOM test dependency for one file.
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

describe('recordRecentFolder / getRecentFolders', () => {
  it('starts empty', () => {
    expect(getRecentFolders()).toEqual([])
  })

  it('prepends the most recently viewed folder', () => {
    recordRecentFolder('a')
    recordRecentFolder('b')
    expect(getRecentFolders()).toEqual(['b', 'a'])
  })

  it('does not record the same folder twice in a row', () => {
    recordRecentFolder('a')
    recordRecentFolder('a')
    recordRecentFolder('a')
    expect(getRecentFolders()).toEqual(['a'])
  })

  it('allows non-consecutive repeats of the same folder', () => {
    recordRecentFolder('a')
    recordRecentFolder('b')
    recordRecentFolder('a')
    expect(getRecentFolders()).toEqual(['a', 'b', 'a'])
  })

  it('caps the list at 10 entries', () => {
    for (let i = 0; i < 15; i++) {
      recordRecentFolder(`folder-${i}`)
    }
    const result = getRecentFolders()
    expect(result).toHaveLength(10)
    expect(result[0]).toBe('folder-14')
  })
})
