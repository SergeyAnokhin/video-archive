// Pure grid-geometry helpers for the preview layout editor (no DOM, no
// network) — the client-side mirror of the backend's canonical
// `compute_layout_tiles()` used for instant editor feedback and preset
// thumbnails; the backend endpoint stays the source of truth for validation.
import type { EnlargedTile, LayoutTile } from '../types/api'

export function cellsOf(tile: EnlargedTile): [number, number][] {
  const cells: [number, number][] = []
  for (let r = tile.row; r < tile.row + tile.span; r++) {
    for (let c = tile.col; c < tile.col + tile.span; c++) cells.push([r, c])
  }
  return cells
}

export function buildOccupancy(rows: number, cols: number, enlarged: EnlargedTile[]): boolean[][] {
  const grid = Array.from({ length: rows }, () => Array(cols).fill(false))
  for (const tile of enlarged) {
    for (const [r, c] of cellsOf(tile)) {
      if (r < rows && c < cols) grid[r][c] = true
    }
  }
  return grid
}

export function fillAll(rows: number, cols: number, span: 2 | 3): EnlargedTile[] {
  const occupied = Array.from({ length: rows }, () => Array(cols).fill(false))
  const tiles: EnlargedTile[] = []
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if (occupied[r][c] || r + span > rows || c + span > cols) continue
      let fits = true
      for (let rr = r; rr < r + span && fits; rr++) {
        for (let cc = c; cc < c + span && fits; cc++) {
          if (occupied[rr][cc]) fits = false
        }
      }
      if (!fits) continue
      tiles.push({ row: r, col: c, span })
      for (let rr = r; rr < r + span; rr++) for (let cc = c; cc < c + span; cc++) occupied[rr][cc] = true
    }
  }
  return tiles
}

export function computeTilesLocal(rows: number, cols: number, enlarged: EnlargedTile[]): LayoutTile[] {
  const occupied = buildOccupancy(rows, cols, enlarged)
  const tiles: LayoutTile[] = enlarged.map((tile) => ({ ...tile, type: 'enlarged' }))
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if (!occupied[r][c]) tiles.push({ row: r, col: c, span: 1, type: 'small' })
    }
  }
  return tiles
}
