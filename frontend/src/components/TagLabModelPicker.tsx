import { ChevronDown } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { ModelPricing, ProviderEntry } from '../types/api'

interface TagLabModelPickerProps {
  entries: ProviderEntry[]
  prices: ModelPricing[]
  value: string
  onChange: (id: string) => void
  disabled: boolean
}

function defaultLabelFor(entry: ProviderEntry): string {
  return `${entry.provider_type}/${entry.vision_model ?? '?'}`
}

function priceFor(entry: ProviderEntry, prices: ModelPricing[]): ModelPricing | undefined {
  return entry.vision_model
    ? prices.find((row) => row.provider_type === entry.provider_type && row.model_name === entry.vision_model)
    : undefined
}

// Row content shared between the closed toggle and each open-list option
// (user request -- stop always appending "(provider/model)" after the name:
// that repeated the exact same text whenever display_name was still the
// auto-generated "{provider}/{model}" default, e.g. the screenshot showing
// "gemini/gemini-3.1-flash-lite (gemini/gemini-3.1-flash-lite)". Now the
// provider/model pair is only shown once, colored to stand apart from a
// genuinely custom display name, and price sits in its own right-aligned
// column. A native <option> can't carry per-part colors or a column layout,
// hence a custom popover instead of <select> below.
function ModelRow({ entry, prices }: { entry: ProviderEntry; prices: ModelPricing[] }) {
  const { t } = useTranslation()
  const hasCustomName = entry.display_name !== defaultLabelFor(entry)
  const price = priceFor(entry, prices)

  return (
    <span className="tag-lab-model-picker__row">
      <span className="tag-lab-model-picker__name">
        {hasCustomName && <span className="tag-lab-model-picker__custom-name">{entry.display_name}</span>}
        <span className="tag-lab-model-picker__pair">
          <span className="tag-lab-model-picker__provider">{entry.provider_type}</span>
          <span className="tag-lab-model-picker__slash">/</span>
          <span className="tag-lab-model-picker__model">{entry.vision_model ?? '?'}</span>
        </span>
      </span>
      <span className="tag-lab-model-picker__price">
        {price?.input_per_million != null && price.output_per_million != null ? (
          <>
            <span className="tag-lab-model-picker__price-in">${price.input_per_million}</span>
            <span className="tag-lab-model-picker__price-slash">/</span>
            <span className="tag-lab-model-picker__price-out">${price.output_per_million}</span>
          </>
        ) : (
          <span className="tag-lab-model-picker__price-empty">{t('tagLab.priceUnavailable')}</span>
        )}
      </span>
    </span>
  )
}

interface ListPosition {
  top: number
  left: number
  width: number
  maxHeight: number
}

export function TagLabModelPicker({ entries, prices, value, onChange, disabled }: TagLabModelPickerProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [listPosition, setListPosition] = useState<ListPosition | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const toggleRef = useRef<HTMLButtonElement | null>(null)
  const selectedEntry = entries.find((entry) => entry.id === value) ?? null

  useEffect(() => {
    if (!open) return
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  // Fixed positioning (computed here, relative to the viewport) instead of
  // absolute-inside-the-modal (user request -- the modal body scrolls, so an
  // absolutely positioned list got clipped by it and grew its own inner
  // scrollbar on top of the modal's, producing two visible scrollbars for
  // one dropdown). Recomputed on scroll/resize so it tracks the toggle.
  useEffect(() => {
    if (!open) return
    function updatePosition() {
      const rect = toggleRef.current?.getBoundingClientRect()
      if (!rect) return
      const margin = 8
      const spaceBelow = window.innerHeight - rect.bottom - margin
      setListPosition({
        top: rect.bottom + 4,
        left: rect.left,
        width: rect.width,
        maxHeight: Math.max(120, spaceBelow),
      })
    }
    updatePosition()
    window.addEventListener('resize', updatePosition)
    window.addEventListener('scroll', updatePosition, true)
    return () => {
      window.removeEventListener('resize', updatePosition)
      window.removeEventListener('scroll', updatePosition, true)
    }
  }, [open])

  return (
    <div className="tag-lab-model-picker" ref={containerRef}>
      <button
        ref={toggleRef}
        type="button"
        className="tag-lab-model-picker__toggle convert-dialog__input"
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
      >
        {selectedEntry ? (
          <ModelRow entry={selectedEntry} prices={prices} />
        ) : (
          <span className="tag-lab-model-picker__placeholder">{t('providerSettings.noModelSelected')}</span>
        )}
        <ChevronDown size={14} className="tag-lab-model-picker__chevron" />
      </button>

      {open && listPosition && (
        <div
          className="tag-lab-model-picker__list"
          role="listbox"
          style={{
            top: listPosition.top,
            left: listPosition.left,
            width: listPosition.width,
            maxHeight: listPosition.maxHeight,
          }}
        >
          {entries.map((entry) => (
            <button
              key={entry.id}
              type="button"
              role="option"
              aria-selected={entry.id === value}
              className={`tag-lab-model-picker__option${entry.id === value ? ' tag-lab-model-picker__option--selected' : ''}`}
              onClick={() => {
                onChange(entry.id)
                setOpen(false)
              }}
            >
              <ModelRow entry={entry} prices={prices} />
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
