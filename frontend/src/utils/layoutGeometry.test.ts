import { describe, expect, it } from 'vitest'
import type { EnlargedTile } from '../types/api'
import { buildOccupancy, cellsOf, computeTilesLocal, fillAll } from './layoutGeometry'

describe('cellsOf', () => {
  it('expands an enlarged tile into all covered cells', () => {
    expect(cellsOf({ row: 1, col: 2, span: 2 })).toEqual([
      [1, 2],
      [1, 3],
      [2, 2],
      [2, 3],
    ])
  })
})

describe('buildOccupancy', () => {
  it('marks covered cells and ignores out-of-bounds overhang', () => {
    const grid = buildOccupancy(2, 2, [{ row: 1, col: 1, span: 2 }])
    expect(grid).toEqual([
      [false, false],
      [false, true],
    ])
  })
})

describe('fillAll', () => {
  it('tiles a 4x4 grid completely with 2x2 tiles', () => {
    const tiles = fillAll(4, 4, 2)
    expect(tiles).toHaveLength(4)
    const covered = new Set(tiles.flatMap((tile) => cellsOf(tile).map(([r, c]) => `${r},${c}`)))
    expect(covered.size).toBe(16)
  })

  it('skips positions where the span does not fit', () => {
    // A 3-span tile only fits once in a 3x5 grid (rows are the limit).
    expect(fillAll(3, 5, 3)).toEqual([{ row: 0, col: 0, span: 3 }])
  })

  it('never overlaps previously placed tiles', () => {
    const tiles = fillAll(5, 5, 2)
    const seen = new Set<string>()
    for (const tile of tiles) {
      for (const [r, c] of cellsOf(tile)) {
        const key = `${r},${c}`
        expect(seen.has(key)).toBe(false)
        seen.add(key)
      }
    }
  })
})

describe('computeTilesLocal', () => {
  it('returns only small tiles for an empty layout', () => {
    const tiles = computeTilesLocal(2, 3, [])
    expect(tiles).toHaveLength(6)
    expect(tiles.every((tile) => tile.type === 'small' && tile.span === 1)).toBe(true)
  })

  it('fills every cell not covered by enlarged tiles, matching the backend contract', () => {
    const enlarged: EnlargedTile[] = [{ row: 0, col: 0, span: 2 }]
    const tiles = computeTilesLocal(3, 3, enlarged)
    // 1 enlarged (covers 4 cells) + 5 small = full 9-cell coverage.
    expect(tiles.filter((tile) => tile.type === 'enlarged')).toHaveLength(1)
    expect(tiles.filter((tile) => tile.type === 'small')).toHaveLength(5)
    const covered = tiles.flatMap((tile) =>
      Array.from({ length: tile.span ** 2 }, (_, i) => {
        const dr = Math.floor(i / tile.span)
        const dc = i % tile.span
        return `${tile.row + dr},${tile.col + dc}`
      }),
    )
    expect(new Set(covered).size).toBe(9)
  })
})
