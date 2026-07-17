import { Save, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { ProviderEntry, ProviderType } from '../types/api'
import { FAL_VISION_MODELS, MODEL_LISTING_SUPPORTED, PROVIDER_TYPES } from './providerCatalog'

interface ProviderEntryFormProps {
  initial: ProviderEntry | null
  onCancel: () => void
  onSaved: () => Promise<void>
}

export function ProviderEntryForm({ initial, onCancel, onSaved }: ProviderEntryFormProps) {
  const { t } = useTranslation()
  const editingExisting = initial !== null
  const [providerType, setProviderType] = useState<ProviderType>(initial?.provider_type ?? 'gemini')
  const [displayName, setDisplayName] = useState(initial?.display_name ?? '')
  const [apiKey, setApiKey] = useState('')
  const [visionModel, setVisionModel] = useState(initial?.vision_model ?? '')
  const [modelOptions, setModelOptions] = useState<string[]>([])
  const [loadingModels, setLoadingModels] = useState(false)
  const [modelError, setModelError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleLoadModels() {
    if (!MODEL_LISTING_SUPPORTED.includes(providerType)) {
      setModelError(t('providerSettings.modelsNotSupported'))
      return
    }
    setLoadingModels(true)
    setModelError(null)
    try {
      const json = editingExisting
        ? await api<{ models?: string[] }>(`/api/settings/provider-entries/${initial.id}/models`, { method: 'POST' })
        : await api<{ models?: string[] }>('/api/settings/provider-entries/models', {
            method: 'POST',
            body: { provider_type: providerType, api_key: apiKey },
          })
      setModelOptions(json.models ?? [])
    } catch (err) {
      setModelError(t('providerSettings.loadModelsError', { error: err instanceof Error ? err.message : String(err) }))
    } finally {
      setLoadingModels(false)
    }
  }

  async function handleSave() {
    setSaving(true)
    setError(null)
    try {
      const name = displayName.trim() || `${providerType}/${visionModel || '?'}`
      const body: Record<string, unknown> = {
        display_name: name,
        enabled: initial?.enabled ?? true,
        vision_model: visionModel || null,
        text_model: initial?.text_model ?? null,
        batch_enabled: initial?.batch_enabled ?? false,
      }
      if (apiKey) body.api_key = apiKey
      if (!editingExisting) body.provider_type = providerType

      const url = editingExisting ? `/api/settings/provider-entries/${initial.id}` : '/api/settings/provider-entries'
      await api(url, { method: editingExisting ? 'PUT' : 'POST', body })
      await onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="provider-entry-form">
      <label className="settings-modal__label">
        {t('providerSettings.providerType')}
        <select
          className="settings-modal__input"
          value={providerType}
          disabled={editingExisting}
          onChange={(event) => setProviderType(event.target.value as ProviderType)}
        >
          {PROVIDER_TYPES.map((type) => (
            <option key={type} value={type}>
              {t(`providers.${type}`)}
            </option>
          ))}
        </select>
      </label>

      <label className="settings-modal__label">
        {t('providerSettings.apiKey')}
        <input
          className="settings-modal__input"
          type="password"
          placeholder={editingExisting && initial.has_api_key ? t('providerSettings.keySetPlaceholder') : ''}
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
        />
      </label>

      <div className="settings-modal__row">
        <label className="settings-modal__label">
          {t('providerSettings.visionModel')}
          <input
            className="settings-modal__input"
            list="provider-entry-model-options"
            value={visionModel}
            onChange={(event) => setVisionModel(event.target.value)}
          />
          <datalist id="provider-entry-model-options">
            {(providerType === 'fal' ? FAL_VISION_MODELS : modelOptions).map((model) => (
              <option key={model} value={model} />
            ))}
          </datalist>
        </label>
        <button
          type="button"
          className="settings-modal__option"
          onClick={() => void handleLoadModels()}
          disabled={loadingModels || !MODEL_LISTING_SUPPORTED.includes(providerType) || (!editingExisting && !apiKey)}
          title={!MODEL_LISTING_SUPPORTED.includes(providerType) ? t('providerSettings.modelsNotSupported') : undefined}
        >
          {loadingModels ? t('providerSettings.loadingModels') : t('providerSettings.loadModels')}
        </button>
      </div>
      {/* The button above is disabled (not clickable) for a provider that doesn't
          support model listing, so handleLoadModels()'s own modelError branch for
          this case is unreachable -- show the same explanation as a static hint
          instead (user report: the button looked silently broken for FAL, which
          has no discoverable model catalog to list -- see providers/fal.py).
          FAL additionally gets a hand-picked starter list in the datalist above
          (FAL_VISION_MODELS) instead of just an empty dropdown. */}
      {providerType === 'fal' && <p className="settings-modal__hint">{t('providerSettings.falModelsHint')}</p>}
      {!MODEL_LISTING_SUPPORTED.includes(providerType) && providerType !== 'fal' && (
        <p className="settings-modal__hint">{t('providerSettings.modelsNotSupported')}</p>
      )}
      {modelError && <p className="settings-modal__hint settings-modal__hint--error">{modelError}</p>}

      <label className="settings-modal__label">
        {t('providerSettings.name')}
        <input
          className="settings-modal__input"
          value={displayName}
          placeholder={t('providerSettings.namePlaceholder')}
          onChange={(event) => setDisplayName(event.target.value)}
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
