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
        {tiles.map((tile) => {
          const key = `${tile.row}-${tile.col}`
          const className = `preview-canvas__tile preview-canvas__tile--${tile.type}`
          const style = {
            gridColumn: `${tile.col + 1} / span ${tile.span}`,
            gridRow: `${tile.row + 1} / span ${tile.span}`,
          }
          // Non-interactive tiles render as <div> — a <button> here would nest
          // inside the preset-card <button> in the gallery, which is invalid HTML.
          return onCellClick ? (
            <button key={key} type="button" className={className} style={style} onClick={() => onCellClick(tile.row, tile.col)} />
          ) : (
            <div key={key} className={className} style={style} />
          )
        })}
      </div>
      {caption !== undefined && <div className="preview-canvas__caption">{caption}</div>}
    </div>
  )
}
