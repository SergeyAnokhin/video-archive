import type { LayoutTile } from '../types/api'
import './PreviewSettingsSection.css'

interface LayoutCanvasProps {
  tiles: LayoutTile[]
  gridRows: number
  gridCols: number
  aspectRatio: number
  caption?: string
  mini?: boolean
  onCellClick?: (row: number, col: number) => void
}

// Black-canvas grid renderer for the preview layout editor: doubles as the
// interactive construction-set surface (with `onCellClick`) and as a static
// mini thumbnail in the preset gallery (`mini`, no click handler).
export function LayoutCanvas({ tiles, gridRows, gridCols, aspectRatio, caption, mini, onCellClick }: LayoutCanvasProps) {
  return (
    <div
      className={mini ? 'preview-canvas preview-canvas--mini' : 'preview-canvas'}
      style={{ aspectRatio: `${aspectRatio}` }}
    >
      <div
        className="preview-canvas__grid"
        style={{ gridTemplateColumns: `repeat(${gridCols}, 1fr)`, gridTemplateRows: `repeat(${gridRows}, 1fr)` }}
      >
        {tiles.map((tile) => (
          <button
            key={`${tile.row}-${tile.col}`}
            type="button"
            className={`preview-canvas__tile preview-canvas__tile--${tile.type}`}
            style={{
              gridColumn: `${tile.col + 1} / span ${tile.span}`,
              gridRow: `${tile.row + 1} / span ${tile.span}`,
            }}
            onClick={onCellClick ? () => onCellClick(tile.row, tile.col) : undefined}
            disabled={!onCellClick}
            tabIndex={onCellClick ? 0 : -1}
          />
        ))}
      </div>
      {caption !== undefined && <div className="preview-canvas__caption">{caption}</div>}
    </div>
  )
}
