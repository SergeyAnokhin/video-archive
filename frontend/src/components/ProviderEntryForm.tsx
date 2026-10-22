import { Save, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { CatalogModel, ModelPricing, ProviderCatalog, ProviderEntry, ProviderStatus, ProviderType } from '../types/api'
import { BATCH_SUPPORTED, FAL_VISION_MODELS, PROVIDER_TYPES } from './providerCatalog'

interface ProviderEntryFormProps {
  initial: ProviderEntry | null
  providers: ProviderStatus[]
  prices: ModelPricing[]
  onCancel: () => void
  onSaved: () => Promise<void>
}

function formatRate(value: number | null | undefined): string {
  return value == null ? '' : String(value)
}

function parseRate(value: string): number | null {
  if (!value.trim()) return null
  const parsed = Number.parseFloat(value)
  return Number.isNaN(parsed) ? Number.NaN : parsed
}

// Everything about one model in one place: which provider (its shared key
// is set in the providers block above, never here), the model picked from
// that provider's cached catalog, its $/1M price, and a free-form comment.
// The price is shared by every entry using the same model; it may be left
// empty and filled later by importing a price file.
export function ProviderEntryForm({ initial, providers, prices, onCancel, onSaved }: ProviderEntryFormProps) {
  const { t } = useTranslation()
  const editingExisting = initial !== null
  const [providerType, setProviderType] = useState<ProviderType>(
    initial?.provider_type ?? providers.find((row) => row.has_api_key)?.provider_type ?? 'gemini',
  )
  const [displayName, setDisplayName] = useState(initial?.display_name ?? '')
  const [visionModel, setVisionModel] = useState(initial?.vision_model ?? '')
  const [textModel, setTextModel] = useState(initial?.text_model ?? '')
  const [batchEnabled, setBatchEnabled] = useState(initial?.batch_enabled ?? false)
  const [notes, setNotes] = useState(initial?.notes ?? '')
  const [catalog, setCatalog] = useState<CatalogModel[]>([])
  const [loadingCatalog, setLoadingCatalog] = useState(false)
  const [priceIn, setPriceIn] = useState('')
  const [priceOut, setPriceOut] = useState('')
  const [priceDirty, setPriceDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const provider = providers.find((row) => row.provider_type === providerType)
  const storedPrice = prices.find((row) => row.provider_type === providerType && row.model_name === visionModel)

  useEffect(() => {
    let cancelled = false
    setCatalog([])
    if (providerType === 'fal') {
      setCatalog(FAL_VISION_MODELS.map((model_id) => ({ model_id, input_per_million: null, output_per_million: null })))
      return
    }
    if (!provider?.catalog_supported || !provider.has_api_key) return
    setLoadingCatalog(true)
    api<ProviderCatalog>(`/api/settings/providers/${providerType}/models`)
      .then((json) => {
        if (!cancelled) setCatalog(json.models)
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setLoadingCatalog(false)
      })
    return () => {
      cancelled = true
    }
  }, [providerType, provider?.catalog_supported, provider?.has_api_key])

  // Show the stored price for the picked model, else the catalog's (OpenRouter
  // publishes prices); the user's own edits win until the model changes.
  useEffect(() => {
    if (priceDirty) return
    const fromCatalog = catalog.find((row) => row.model_id === visionModel)
    setPriceIn(formatRate(storedPrice?.input_per_million ?? fromCatalog?.input_per_million))
    setPriceOut(formatRate(storedPrice?.output_per_million ?? fromCatalog?.output_per_million))
  }, [visionModel, catalog, storedPrice, priceDirty])

  async function handleSave() {
    const inputRate = parseRate(priceIn)
    const outputRate = parseRate(priceOut)
    if (Number.isNaN(inputRate) || Number.isNaN(outputRate) || (inputRate === null) !== (outputRate === null)) {
      setError(t('providerSettings.priceBothOrNone'))
      return
    }
    setSaving(true)
    setError(null)
    try {
      const name = displayName.trim() || `${providerType}/${visionModel || '?'}`
      const body: Record<string, unknown> = {
        display_name: name,
        enabled: initial?.enabled ?? true,
        vision_model: visionModel || null,
        text_model: textModel || null,
        batch_enabled: BATCH_SUPPORTED.includes(providerType) && batchEnabled,
        notes: notes.trim() || null,
      }
      if (!editingExisting) body.provider_type = providerType

      const url = editingExisting ? `/api/settings/provider-entries/${initial.id}` : '/api/settings/provider-entries'
      await api(url, { method: editingExisting ? 'PUT' : 'POST', body })
      if (priceDirty && visionModel && inputRate !== null && outputRate !== null) {
        await api('/api/settings/model-pricing', {
          method: 'PUT',
          body: {
            provider_type: providerType,
            model_name: visionModel,
            input_per_million: inputRate,
            output_per_million: outputRate,
          },
        })
      }
      await onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  function modelOptionLabel(model: CatalogModel): string | undefined {
    if (model.input_per_million == null || model.output_per_million == null) return undefined
    return t('providerSettings.catalogPrice', { input: model.input_per_million, output: model.output_per_million })
  }

  const datalistId = `provider-entry-models-${initial?.id ?? 'new'}`

  return (
    <div className="provider-entry-form">
      <div className="settings-modal__row">
        <label className="settings-modal__label">
          {t('providerSettings.providerType')}
          <select
            className="settings-modal__input"
            value={providerType}
            disabled={editingExisting}
            onChange={(event) => {
              setProviderType(event.target.value as ProviderType)
              setPriceDirty(false)
            }}
          >
            {PROVIDER_TYPES.map((type) => (
              <option key={type} value={type}>
                {t(`providers.${type}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="settings-modal__label">
          {t('providerSettings.name')}
          <input
            className="settings-modal__input"
            value={displayName}
            placeholder={t('providerSettings.namePlaceholder')}
            onChange={(event) => setDisplayName(event.target.value)}
          />
        </label>
      </div>
      {provider && !provider.has_api_key && (
        <p className="settings-modal__hint settings-modal__hint--warning">{t('providerSettings.providerKeyMissing')}</p>
      )}

      <label className="settings-modal__label">
        {t('providerSettings.visionModel')}
        <input
          className="settings-modal__input"
          list={datalistId}
          value={visionModel}
          placeholder={loadingCatalog ? t('providerSettings.loadingModels') : t('providerSettings.modelPlaceholder')}
          onChange={(event) => {
            setVisionModel(event.target.value)
            setPriceDirty(false)
          }}
        />
        <datalist id={datalistId}>
          {catalog.map((model) => (
            <option key={model.model_id} value={model.model_id} label={modelOptionLabel(model)} />
          ))}
        </datalist>
      </label>
      {providerType === 'fal' && <p className="settings-modal__hint">{t('providerSettings.falModelsHint')}</p>}
      {provider?.catalog_supported && provider.has_api_key && !loadingCatalog && catalog.length === 0 && (
        <p className="settings-modal__hint">{t('providerSettings.catalogEmpty')}</p>
      )}

      <div className="settings-modal__row">
        <label className="settings-modal__label">
          {t('providerSettings.priceInput')}
          <input
            type="number"
            step="any"
            min="0"
            className="settings-modal__input"
            value={priceIn}
            placeholder={t('providerSettings.priceNotSet')}
            disabled={!visionModel}
            onChange={(event) => {
              setPriceIn(event.target.value)
              setPriceDirty(true)
            }}
          />
        </label>
        <label className="settings-modal__label">
          {t('providerSettings.priceOutput')}
          <input
            type="number"
            step="any"
            min="0"
            className="settings-modal__input"
            value={priceOut}
            placeholder={t('providerSettings.priceNotSet')}
            disabled={!visionModel}
            onChange={(event) => {
              setPriceOut(event.target.value)
              setPriceDirty(true)
            }}
          />
        </label>
      </div>
      <p className="settings-modal__hint">
        {storedPrice
          ? t('providerSettings.priceSource', { source: t(`modelPricing.source.${storedPrice.source}`) })
          : t('providerSettings.priceHint')}
      </p>

      <label className="settings-modal__label">
        {t('providerSettings.textModel')}
        <input
          className="settings-modal__input"
          list={datalistId}
          value={textModel}
          onChange={(event) => setTextModel(event.target.value)}
        />
      </label>

      {BATCH_SUPPORTED.includes(providerType) && (
        <label className="settings-modal__field">
          <span className="settings-modal__field-label">{t('providerSettings.batchEnabled')}</span>
          <input type="checkbox" checked={batchEnabled} onChange={(event) => setBatchEnabled(event.target.checked)} />
        </label>
      )}

      <label className="settings-modal__label">
        {t('providerSettings.notes')}
        <textarea
          className="settings-modal__input provider-entry-form__notes"
          rows={2}
          value={notes}
          placeholder={t('providerSettings.notesPlaceholder')}
          onChange={(event) => setNotes(event.target.value)}
        />
      </label>

      {error && <p className="settings-modal__hint settings-modal__hint--error">{error}</p>}

      <div className="settings-modal__actions">
        <button type="button" className="settings-modal__option" onClick={() => void handleSave()} disabled={saving}>
          <Save size={14} /> {t('providerSettings.save')}
        </button>
        <button type="button" className="settings-modal__option" onClick={onCancel}>
          <X size={14} /> {t('providerSettings.cancel')}
        </button>
      </div>
    </div>
  )
}
