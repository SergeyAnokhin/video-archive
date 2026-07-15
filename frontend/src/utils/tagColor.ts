// Cheerful, high-contrast-on-dark palette (Design System dark surfaces) so
// tags stay easy to tell apart even with 20-30 of them on screen at once.
// Mirrors `backend/app/tags.py`'s `resolve_tag_color()` exactly (same
// palette, same hash fold) so a tag with no explicit color gets the same
// deterministic color server- and client-side.
const FALLBACK_PALETTE = [
  '#ff6b6b',
  '#f59f00',
  '#ffd43b',
  '#69db7c',
  '#38d9a9',
  '#4dabf7',
  '#748ffc',
  '#da77f2',
  '#f783ac',
  '#ff922b',
  '#20c997',
  '#22b8cf',
]

export function hashTagColor(id: string): string {
  let hash = 0
  for (let i = 0; i < id.length; i++) {
    hash = (hash * 31 + id.charCodeAt(i)) | 0
  }
  return FALLBACK_PALETTE[Math.abs(hash) % FALLBACK_PALETTE.length]
}

function srgbToLinear(channel: number): number {
  const c = channel / 255
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
}

function relativeLuminance(hex: string): number {
  const normalized = hex.replace('#', '')
  const full =
    normalized.length === 3
      ? normalized
          .split('')
          .map((ch) => ch + ch)
          .join('')
      : normalized.padEnd(6, '0').slice(0, 6)
  const r = Number.parseInt(full.slice(0, 2), 16)
  const g = Number.parseInt(full.slice(2, 4), 16)
  const b = Number.parseInt(full.slice(4, 6), 16)
  return 0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b)
}

// Simple mid-point threshold against the badge's own background -- good
// enough for a small colored chip (not full-page body text), and keeps the
// formula easy to reason about.
export function getContrastTextColor(hex: string | null | undefined): '#000000' | '#ffffff' {
  if (!hex) {
    return '#ffffff'
  }
  return relativeLuminance(hex) > 0.5 ? '#000000' : '#ffffff'
}
