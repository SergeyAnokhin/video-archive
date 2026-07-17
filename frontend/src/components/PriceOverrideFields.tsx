import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { tryApi } from '../api/client'
import type { ModelPricing, ProviderEntry } from '../types/api'

// Per-entry price override, right where the model itself is configured
// (user request -- editing a model's $/1M rate shouldn't require scrolling
// down to the separate pricing table below, especially for a model that has
// no row there yet, e.g. a newly released Gemini id the static seed table
// doesn't know about). Reads/writes the same `model_pricing` table as
// `ModelPricingSection` (keyed by provider_type + model_name, shared across
// every entry pointing at that model), scoped to the entry's vision model
// since that's what Tag Lab/tagging actually calls.
export function PriceOverrideFields({
  entry,
  prices,
  onSaved,
}: {
  entry: ProviderEntry
  prices: ModelPricing[]
  onSaved: () => Promise<void>
}) {
  const { t } = useTranslation()
  const modelName = entry.vision_model
  const price = modelName
    ? prices.find((row) => row.provider_type === entry.provider_type && row.model_name === modelName)
    : undefined
  const [saving, setSaving] = useState(false)

  async function handleSave(changes: { input_per_million?: number; output_per_million?: number }) {
    if (!modelName) return
    setSaving(true)
    try {
      const body = {
        provider_type: entry.provider_type,
        model_name: modelName,
        input_per_million: price?.input_per_million ?? 0,
        output_per_million: price?.output_per_million ?? 0,
        ...changes,
      }
      const saved = await tryApi('/api/settings/model-pricing', { method: 'PUT', body })
      if (saved !== null) await onSaved()
    } finally {
      setSaving(false)
    }
  }

  if (!modelName) {
    return <p className="settings-modal__hint">{t('providerSettings.priceNoModel')}</p>
  }

  return (
    <div className="provider-entry-row__price">
      <span className="settings-modal__field-label">{t('providerSettings.priceLabel', { model: modelName })}</span>
      <div className="settings-modal__row">
        <label className="settings-modal__label">
          {t('providerSettings.priceInput')}
          <input
            key={`${modelName}-input`}
            type="number"
            step="any"
            className="settings-modal__input"
            defaultValue={price?.input_per_million ?? ''}
            placeholder={t('providerSettings.priceNotSet')}
            disabled={saving}
            onBlur={(event) => {
              const value = Number.parseFloat(event.target.value)
              if (!Number.isNaN(value)) void handleSave({ input_per_million: value })
            }}
          />
        </label>
        <label className="settings-modal__label">
          {t('providerSettings.priceOutput')}
          <input
            key={`${modelName}-output`}
            type="number"
            step="any"
            className="settings-modal__input"
            defaultValue={price?.output_per_million ?? ''}
            placeholder={t('providerSettings.priceNotSet')}
            disabled={saving}
            onBlur={(event) => {
              const value = Number.parseFloat(event.target.value)
              if (!Number.isNaN(value)) void handleSave({ output_per_million: value })
            }}
          />
        </label>
      </div>
    </div>
  )
}
