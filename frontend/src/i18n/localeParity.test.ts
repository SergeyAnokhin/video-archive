// CLAUDE.md / docs/development.md require en.json and ru.json to stay in
// parity whenever UI copy changes. This enforces it instead of relying on a
// manual ad-hoc key diff at review time: same key set, both directions,
// including nested groups.
import { describe, expect, it } from 'vitest'
import en from './locales/en.json'
import ru from './locales/ru.json'

function flattenKeys(value: unknown, prefix = ''): string[] {
  if (typeof value !== 'object' || value === null) {
    return [prefix]
  }
  return Object.entries(value).flatMap(([key, child]) =>
    flattenKeys(child, prefix ? `${prefix}.${key}` : key),
  )
}

describe('locale parity', () => {
  it('en.json and ru.json expose the same key set', () => {
    const enKeys = flattenKeys(en).sort()
    const ruKeys = flattenKeys(ru).sort()
    expect(ruKeys).toEqual(enKeys)
  })
})
