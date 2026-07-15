import { X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { getContrastTextColor, hashTagColor } from '../utils/tagColor'
import './TagBadge.css'

interface TagBadgeProps {
  displayName: string
  // Falls back to a deterministic hash color client-side (matches the
  // backend's own fallback in `resolve_tag_color()`) in the unlikely case a
  // caller doesn't have a resolved color yet -- the API always sends one.
  color?: string | null
  inactive?: boolean
  title?: string
  scoreLabel?: string
  onClick?: () => void
  onDoubleClick?: () => void
  onColorChange?: (color: string) => void
  onRemove?: () => void
  removeLabel?: string
}

export function TagBadge({
  displayName,
  color,
  inactive,
  title,
  scoreLabel,
  onClick,
  onDoubleClick,
  onColorChange,
  onRemove,
  removeLabel,
}: TagBadgeProps) {
  const { t } = useTranslation()
  const resolvedColor = color || hashTagColor(displayName)
  const textColor = getContrastTextColor(resolvedColor)
  const clickable = Boolean(onClick || onDoubleClick)

  return (
    <span
      className={`tag-badge${inactive ? ' tag-badge--inactive' : ''}`}
      style={{ background: resolvedColor, color: textColor }}
      title={title}
    >
      {onColorChange && (
        <span className="tag-badge__swatch" style={{ borderColor: textColor }}>
          <input
            type="color"
            className="tag-badge__color-input"
            value={resolvedColor}
            onClick={(event) => event.stopPropagation()}
            onChange={(event) => onColorChange(event.target.value)}
            aria-label={t('tagging.pickColor', { name: displayName })}
            title={t('tagging.pickColor', { name: displayName })}
          />
        </span>
      )}
      {clickable ? (
        <button type="button" className="tag-badge__label" onClick={onClick} onDoubleClick={onDoubleClick}>
          {displayName}
        </button>
      ) : (
        <span className="tag-badge__label tag-badge__label--static">{displayName}</span>
      )}
      {scoreLabel && <span className="tag-badge__score">{scoreLabel}</span>}
      {onRemove && (
        <button
          type="button"
          className="tag-badge__remove"
          onClick={onRemove}
          aria-label={removeLabel ?? t('tagging.delete')}
          title={removeLabel ?? t('tagging.delete')}
        >
          <X size={12} />
        </button>
      )}
    </span>
  )
}
