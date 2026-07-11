import { describe, expect, it } from 'vitest'
import { formatSearchQuery, parseSearchQuery } from './searchQuery'

describe('parseSearchQuery', () => {
  it('treats plain text as an all-scope query', () => {
    expect(parseSearchQuery('birthday')).toEqual({ scope: 'all', term: 'birthday' })
    expect(parseSearchQuery('  birthday  ')).toEqual({ scope: 'all', term: 'birthday' })
  })

  it('recognizes tag:/file:/path: prefixes', () => {
    expect(parseSearchQuery('tag:garden')).toEqual({ scope: 'tag', term: 'garden' })
    expect(parseSearchQuery('file:party')).toEqual({ scope: 'file', term: 'party' })
    expect(parseSearchQuery('path:family')).toEqual({ scope: 'path', term: 'family' })
  })

  it('is case-insensitive and tolerates spaces around the prefix', () => {
    expect(parseSearchQuery('TAG: garden')).toEqual({ scope: 'tag', term: 'garden' })
    expect(parseSearchQuery(' File :party')).toEqual({ scope: 'file', term: 'party' })
  })

  it('accepts russian prefix aliases', () => {
    expect(parseSearchQuery('тег:сад')).toEqual({ scope: 'tag', term: 'сад' })
    expect(parseSearchQuery('файл:праздник')).toEqual({ scope: 'file', term: 'праздник' })
    expect(parseSearchQuery('путь:семья')).toEqual({ scope: 'path', term: 'семья' })
  })

  it('leaves unknown prefixes as part of the search term', () => {
    expect(parseSearchQuery('name:party')).toEqual({ scope: 'all', term: 'name:party' })
    // a leading colon is not a prefix
    expect(parseSearchQuery(':party')).toEqual({ scope: 'all', term: ':party' })
  })

  it('keeps later colons inside the term', () => {
    expect(parseSearchQuery('file:a:b')).toEqual({ scope: 'file', term: 'a:b' })
  })

  it('returns an empty term for a bare prefix', () => {
    expect(parseSearchQuery('tag:')).toEqual({ scope: 'tag', term: '' })
  })
})

describe('formatSearchQuery', () => {
  it('round-trips with parseSearchQuery', () => {
    expect(formatSearchQuery('all', 'birthday')).toBe('birthday')
    expect(formatSearchQuery('tag', 'garden')).toBe('tag:garden')
    expect(parseSearchQuery(formatSearchQuery('path', 'family'))).toEqual({ scope: 'path', term: 'family' })
  })
})
