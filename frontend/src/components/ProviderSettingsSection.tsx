import { Download, GripVertical, Pencil, Plus, RefreshCw, Settings, Trash2, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, rawApi, tryApi } from '../api/client'
import type { ModelPricing, ProviderEntry } from '../types/api'
import { ModelPricingSection } from './ModelPricingSection'
import { PriceOverrideFields } from './PriceOverrideFields'
import { ProviderEntryForm } from './ProviderEntryForm'
import { ProviderUsageSection } from './ProviderUsageSection'
import { BATCH_SUPPORTED, MODEL_LISTING_SUPPORTED } from './providerCatalog'

type FormValue = ProviderEntry | 'new' | null

export function ProviderSettingsSection() {
  const { t } = useTranslation()
  const [entries, setEntries] = useState<ProviderEntry[]>([])
  const [editing, setEditing] = useState<FormValue>(null)
  const [advancedId, setAdvancedId] = useState<string | null>(null)
  const [advancedModelOptions, setAdvancedModelOptions] = useState<string[]>([])
  const [loadingAdvancedModels, setLoadingAdvancedModels] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null)
  const [prices, setPrices] = useState<ModelPricing[]>([])
  const importInputRef = useRef<HTMLInputElement>(null)

  async function refresh() {
    const json = await tryApi<{ entries: ProviderEntry[] }>('/api/settings/provider-entries')
    if (json) {
      setEntries(json.entries)
    }
  }

  async function refreshPrices() {
    const json = await tryApi<{ prices: ModelPricing[] }>('/api/settings/model-pricing')
    if (json) {
      setPrices(json.prices)
    }
  }

  useEffect(() => {
    void refresh()
    void refreshPrices()
  }, [])

  async function handleLoadAdvancedModels(entry: ProviderEntry) {
    if (!MODEL_LISTING_SUPPORTED.includes(entry.provider_type)) return
    setLoadingAdvancedModels(true)
    try {
      const json = await tryApi<{ models?: string[] }>(`/api/settings/provider-entries/${entry.id}/models`, {
        method: 'POST',
      })
      if (json) setAdvancedModelOptions(json.models ?? [])
    } finally {
      setLoadingAdvancedModels(false)
    }
  }

  async function handleUpdate(entry: ProviderEntry, changes: Partial<ProviderEntry> & { api_key?: string }) {
    setBusyId(entry.id)
    try {
      const body = {
        display_name: entry.display_name,
        enabled: entry.enabled,
        vision_model: entry.vision_model,
        text_model: entry.text_model,
        batch_enabled: entry.batch_enabled,
        ...changes,
      }
      const saved = await tryApi(`/api/settings/provider-entries/${entry.id}`, { method: 'PUT', body })
      if (saved !== null) await refresh()
    } finally {
      setBusyId(null)
    }
  }

  async function handleDelete(entry: ProviderEntry) {
    if (!window.confirm(t('providerSettings.confirmDelete'))) return
    setBusyId(entry.id)
    try {
      await tryApi(`/api/settings/provider-entries/${entry.id}`, { method: 'DELETE' })
      await refresh()
    } finally {
      setBusyId(null)
    }
  }

  async function handleReorder(fromIndex: number, toIndex: number) {
    if (fromIndex === toIndex) return
    const reordered = [...entries]
    const [moved] = reordered.splice(fromIndex, 1)
    reordered.splice(toIndex, 0, moved)
    await tryApi('/api/settings/provider-entries/reorder', {
      method: 'POST',
      body: { ordered_ids: reordered.map((entry) => entry.id) },
    })
    await refresh()
  }

  async function handleExport() {
    if (!window.confirm(t('providerSettings.exportConfirm'))) return
    const res = await rawApi('/api/settings/provider-entries/export')
    if (!res.ok) return
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'provider-entries-export.json'
    anchor.click()
    URL.revokeObjectURL(url)
  }

  async function handleImportFile(file: File) {
    if (!window.confirm(t('providerSettings.importConfirm'))) return
    try {
      const parsed = JSON.parse(await file.text())
      const json = await api<{ entries: ProviderEntry[]; skipped: number }>('/api/settings/provider-entries/import', {
        method: 'POST',
        body: { entries: parsed.entries ?? [] },
      })
      await refresh()
      window.alert(
        json.skipped > 0
          ? t('providerSettings.importResultWithSkipped', { count: json.entries.length, skipped: json.skipped })
          : t('providerSettings.importResult', { count: json.entries.length }),
      )
    } catch {
      window.alert(t('providerSettings.importError'))
    }
  }

  return (
    <>
    <section className="settings-modal__section">
      <h3 className="settings-modal__section-title">{t('providerSettings.title')}</h3>
      <p className="settings-modal__hint">{t('providerSettings.hint')}</p>

      {entries.length === 0 && <p className="settings-modal__hint">{t('providerSettings.empty')}</p>}

      {entries.map((entry, index) => (
        <div
          key={entry.id}
          className={[
            'provider-entry-row',
            dragIndex === index ? 'provider-entry-row--dragging' : '',
            dragOverIndex === index && dragIndex !== null && dragIndex !== index ? 'provider-entry-row--drag-over' : '',
          ]
            .filter(Boolean)
            .join(' ')}
          onDragOver={(event) => {
            if (dragIndex === null) return
            event.preventDefault()
            setDragOverIndex(index)
          }}
          onDragLeave={() => setDragOverIndex((current) => (current === index ? null : current))}
          onDrop={(event) => {
            event.preventDefault()
            if (dragIndex !== null) void handleReorder(dragIndex, index)
            setDragIndex(null)
            setDragOverIndex(null)
          }}
        >
          <div className="provider-entry-row__main">
            <div
              className="provider-entry-row__handle"
              draggable
              onDragStart={(event) => {
                setDragIndex(index)
                event.dataTransfer.effectAllowed = 'move'
              }}
              onDragEnd={() => {
                setDragIndex(null)
                setDragOverIndex(null)
              }}
              aria-label={t('providerSettings.dragHandle')}
              title={t('providerSettings.dragHandle')}
            >
              <GripVertical size={16} />
            </div>

            <div className="provider-entry-row__info">
              <span className="settings-modal__field-label">{entry.display_name}</span>
              <p className="settings-modal__hint">
                {t(`providers.${entry.provider_type}`)}/{entry.vision_model ?? t('providerSettings.noModelSelected')}
                {entry.key_suffix ? ` [${t('providerSettings.keySuffixLabel', { suffix: entry.key_suffix })}]` : ''}
              </p>
            </div>

            <label className="provider-card__toggle">
              {t('providerSettings.enabled')}
              <input
                type="checkbox"
                checked={entry.enabled}
                onChange={(event) => void handleUpdate(entry, { enabled: event.target.checked })}
                disabled={busyId === entry.id}
              />
            </label>

            <div className="settings-modal__actions">
              <button
                type="button"
                className="settings-modal__option settings-modal__option--icon"
                onClick={() => setEditing(entry)}
                aria-label={t('providerSettings.edit')}
                title={t('providerSettings.edit')}
              >
                <Pencil size={14} />
              </button>
              <button
                type="button"
                className="settings-modal__option settings-modal__option--icon"
                onClick={() => {
                  setAdvancedModelOptions([])
                  setAdvancedId(advancedId === entry.id ? null : entry.id)
                }}
                aria-pressed={advancedId === entry.id}
                aria-label={t('providerSettings.settings')}
                title={t('providerSettings.settings')}
              >
                <Settings size={14} />
              </button>
              <button
                type="button"
                className="settings-modal__option settings-modal__option--icon"
                onClick={() => void handleDelete(entry)}
                disabled={busyId === entry.id}
                aria-label={t('providerSettings.delete')}
                title={t('providerSettings.delete')}
              >
                <Trash2 size={14} />
              </button>
            </div>
          </div>

          {advancedId === entry.id && (
            <div className="provider-entry-row__advanced">
              <div className="settings-modal__row">
                <label className="settings-modal__label">
                  {t('providerSettings.textModel')}
                  <input
                    className="settings-modal__input"
                    list={`provider-entry-text-model-options-${entry.id}`}
                    defaultValue={entry.text_model ?? ''}
                    onBlur={(event) => void handleUpdate(entry, { text_model: event.target.value || null })}
                  />
                  <datalist id={`provider-entry-text-model-options-${entry.id}`}>
                    {advancedModelOptions.map((model) => (
                      <option key={model} value={model} />
                    ))}
                  </datalist>
                </label>
                {MODEL_LISTING_SUPPORTED.includes(entry.provider_type) && (
                  <button
                    type="button"
                    className="settings-modal__option"
                    onClick={() => void handleLoadAdvancedModels(entry)}
                    disabled={loadingAdvancedModels}
                  >
                    <RefreshCw size={14} />
                    {loadingAdvancedModels ? t('providerSettings.loadingModels') : t('providerSettings.loadModels')}
                  </button>
                )}
              </div>
              {BATCH_SUPPORTED.includes(entry.provider_type) && (
                <label className="settings-modal__field">
                  <span className="settings-modal__field-label">{t('providerSettings.batchEnabled')}</span>
                  <input
                    type="checkbox"
                    checked={entry.batch_enabled}
                    onChange={(event) => void handleUpdate(entry, { batch_enabled: event.target.checked })}
                  />
                </label>
              )}
              <PriceOverrideFields entry={entry} prices={prices} onSaved={refreshPrices} />
            </div>
          )}

          {editing !== 'new' && editing?.id === entry.id && (
            <ProviderEntryForm
              initial={editing}
              onCancel={() => setEditing(null)}
              onSaved={async () => {
                setEditing(null)
                await refresh()
              }}
            />
          )}
        </div>
      ))}

      {editing === null && (
        <div className="settings-modal__actions">
          <button type="button" className="settings-modal__option" onClick={() => setEditing('new')}>
            <Plus size={14} /> {t('providerSettings.addProvider')}
          </button>
          <button type="button" className="settings-modal__option" onClick={() => importInputRef.current?.click()}>
            <Upload size={14} /> {t('providerSettings.import')}
          </button>
          <input
            ref={importInputRef}
            type="file"
            accept="application/json"
            style={{ display: 'none' }}
            onChange={(event) => {
              const file = event.target.files?.[0]
              event.target.value = ''
              if (file) void handleImportFile(file)
            }}
          />
          <button type="button" className="settings-modal__option" onClick={() => void handleExport()}>
            <Download size={14} /> {t('providerSettings.export')}
          </button>
        </div>
      )}
      {editing === 'new' && (
        <ProviderEntryForm
          initial={null}
          onCancel={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null)
            await refresh()
          }}
        />
      )}
      {editing === null && entries.length > 0 && (
        <p className="settings-modal__hint">{t('providerSettings.exportWarning')}</p>
      )}
    </section>
    <ModelPricingSection prices={prices} onRefresh={refreshPrices} />
    <ProviderUsageSection />
    </>
  )
}
