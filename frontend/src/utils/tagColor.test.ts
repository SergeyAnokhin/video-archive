import { describe, expect, it } from 'vitest'
import { getContrastTextColor, hashTagColor } from './tagColor'

describe('hashTagColor', () => {
  it('is stable for the same id', () => {
    expect(hashTagColor('same-id')).toBe(hashTagColor('same-id'))
  })

  it('returns a color from the fallback palette', () => {
    expect(hashTagColor('tag-1')).toMatch(/^#[0-9a-f]{6}$/)
  })
})

describe('getContrastTextColor', () => {
  it('uses black text on a light background', () => {
    expect(getContrastTextColor('#ffffff')).toBe('#000000')
  })

  it('uses white text on a dark background', () => {
    expect(getContrastTextColor('#000000')).toBe('#ffffff')
  })

  it('uses black text on a light yellow background', () => {
    expect(getContrastTextColor('#ffd43b')).toBe('#000000')
  })

  it('uses white text on a saturated blue background', () => {
    expect(getContrastTextColor('#4dabf7')).toBe('#ffffff')
  })

  it('falls back to white text when no color is given', () => {
    expect(getContrastTextColor(null)).toBe('#ffffff')
    expect(getContrastTextColor(undefined)).toBe('#ffffff')
  })
})
