import { describe, expect, it } from 'vitest'
import type { Tag } from '../types/api'
import { buildTagSuggestions } from './tagSuggestions'

function makeTag(id: string, displayName: string): Tag {
  return {
    id,
    tag_key: displayName.toLowerCase(),
    display_name: displayName,
    is_active: true,
    is_ai_vocabulary: false,
    is_user_defined: false,
    sort_order: 0,
    color: '#123456',
    created_at: '',
    updated_at: '',
  }
}

describe('buildTagSuggestions', () => {
  const beach = makeTag('1', 'Beach')
  const snow = makeTag('2', 'Snow')
  const forest = makeTag('3', 'Forest')
  const lake = makeTag('4', 'Lake')
  // pool is assumed already usage-ordered (most popular first)
  const pool = [beach, snow, forest, lake]

  it('puts recently manually-added tags first, then fills with the rest of the pool', () => {
    expect(buildTagSuggestions(['Forest'], pool)).toEqual([forest, beach, snow, lake])
  })

  it('falls back to pure popularity order when nothing was recently added', () => {
    expect(buildTagSuggestions([], pool)).toEqual(pool)
  })

  it('ignores a recent name that is no longer in the pool (e.g. filtered out or deleted)', () => {
    expect(buildTagSuggestions(['Mountain'], pool)).toEqual(pool)
  })

  it('matches recent names case-insensitively', () => {
    expect(buildTagSuggestions(['forest'], pool)).toEqual([forest, beach, snow, lake])
  })

  it('caps each block independently at perBlockLimit', () => {
    const bigPool = Array.from({ length: 15 }, (_, i) => makeTag(String(i), `tag-${i}`))
    const recentNames = ['tag-10', 'tag-11', 'tag-12']
    const result = buildTagSuggestions(recentNames, bigPool, 2)
    // recent block capped at 2, then popular block (excluding the ones
    // already used) capped at 2 more -> 4 total
    expect(result).toEqual([
      bigPool[10],
      bigPool[11],
      bigPool[0],
      bigPool[1],
    ])
  })

  it('never lists the same tag twice even if it would qualify for both blocks', () => {
    const result = buildTagSuggestions(['Beach'], pool, 10)
    expect(result.filter((tag) => tag.id === beach.id)).toHaveLength(1)
  })
})
