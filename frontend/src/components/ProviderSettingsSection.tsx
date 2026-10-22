import { Download, FileJson, GripVertical, MessageSquare, Pencil, Plus, Trash2, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, rawApi, tryApi } from '../api/client'
import type { ModelPricing, ProviderEntry, ProviderStatus, ProviderUsageSummary } from '../types/api'
import { ProviderEntryForm } from './ProviderEntryForm'
import { ProviderKeysSection } from './ProviderKeysSection'
import { ProviderUsageSection } from './ProviderUsageSection'

type FormValue = ProviderEntry | 'new' | null
type ProvidersResponse = { providers: ProviderStatus[] }

interface CatalogImportResult {
  updated: { provider_type: string; model_name: string }[]
  unchanged: number
}

export function ProviderSettingsSection() {
  const { t } = useTranslation()
  const [entries, setEntries] = useState<ProviderEntry[]>([])
  const [providers, setProviders] = useState<ProviderStatus[]>([])
  const [refreshingCatalogs, setRefreshingCatalogs] = useState(false)
  const [editing, setEditing] = useState<FormValue>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null)
  const [prices, setPrices] = useState<ModelPricing[]>([])
  const [usage, setUsage] = useState<ProviderUsageSummary[]>([])
  const [priceImportMessage, setPriceImportMessage] = useState<string | null>(null)
  const importInputRef = useRef<HTMLInputElement>(null)
  const priceImportInputRef = useRef<HTMLInputElement>(null)

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

  // Catalogs refresh themselves at most once a day (backend-side); opening
  // this tab is what triggers that check, `force` is the manual button.
  async function refreshCatalogs(force: boolean) {
    setRefreshingCatalogs(true)
    try {
      const json = await tryApi<ProvidersResponse>(
        `/api/settings/providers/refresh-catalogs${force ? '?force=true' : ''}`,
        { method: 'POST' },
      )
      if (json) setProviders(json.providers)
      // An OpenRouter refresh also updates configured models' prices.
      await refreshPrices()
    } finally {
      setRefreshingCatalogs(false)
    }
  }

  useEffect(() => {
    void refresh()
    void refreshPrices()
    void tryApi<ProvidersResponse>('/api/settings/providers').then((json) => {
      if (json) setProviders(json.providers)
    })
    void tryApi<{ usage: ProviderUsageSummary[] }>('/api/settings/provider-usage').then((json) => {
      if (json) setUsage(json.usage)
    })
    void refreshCatalogs(false)
  }, [])

  async function handleToggleEnabled(entry: ProviderEntry, enabled: boolean) {
    setBusyId(entry.id)
    try {
      const body = {
        display_name: entry.display_name,
        enabled,
        vision_model: entry.vision_model,
        text_model: entry.text_model,
        batch_enabled: entry.batch_enabled,
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
      const json = await api<{ entries: ProviderEntry[]; skipped: number; prices_imported: number }>(
        '/api/settings/provider-entries/import',
        {
          method: 'POST',
          body: {
            entries: parsed.entries ?? [],
            model_pricing: parsed.model_pricing ?? [],
            provider_keys: parsed.provider_keys ?? {},
          },
        },
      )
      await refresh()
      await refreshPrices()
      const providersJson = await tryApi<ProvidersResponse>('/api/settings/providers')
      if (providersJson) setProviders(providersJson.providers)
      const base =
        json.skipped > 0
          ? t('providerSettings.importResultWithSkipped', { count: json.entries.length, skipped: json.skipped })
          : t('providerSettings.importResult', { count: json.entries.length })
      const message =
        json.prices_imported > 0
          ? `${base} ${t('providerSettings.importResultPrices', { count: json.prices_imported })}`
          : base
      window.alert(message)
    } catch {
      window.alert(t('providerSettings.importError'))
    }
  }

  async function handleImportPriceFile(file: File) {
    setPriceImportMessage(null)
    try {
      const catalog = JSON.parse(await file.text())
      const json = await api<CatalogImportResult>('/api/settings/model-pricing/import-catalog', {
        method: 'POST',
        body: catalog,
      })
      setPriceImportMessage(
        t('modelPricing.importResult', { updated: json.updated.length, unchanged: json.unchanged }),
      )
      await refreshPrices()
    } catch {
      window.alert(t('modelPricing.importError'))
    }
  }

  function priceFor(entry: ProviderEntry): ModelPricing | undefined {
    return entry.vision_model
      ? prices.find((row) => row.provider_type === entry.provider_type && row.model_name === entry.vision_model)
      : undefined
  }

  function usageFor(entry: ProviderEntry): ProviderUsageSummary | undefined {
    return entry.vision_model
      ? usage.find((row) => row.provider_type === entry.provider_type && row.model_name === entry.vision_model)
      : undefined
  }

  function renderSummary(entry: ProviderEntry) {
    const price = priceFor(entry)
    const stats = usageFor(entry)
    const hasPrice = price?.input_per_million != null && price.output_per_million != null
    return (
      <p className="settings-modal__hint provider-entry-row__summary">
        {hasPrice ? (
          <span>{t('providerSettings.priceShort', { input: price.input_per_million, output: price.output_per_million })}</span>
        ) : (
          entry.vision_model && <span className="provider-entry-row__no-price">{t('providerSettings.noPrice')}</span>
        )}
        {stats && (
          <span>
            {stats.total_estimated_cost_usd != null
              ? t('providerSettings.usageShortWithCost', {
                  calls: stats.call_count,
                  cost: stats.total_estimated_cost_usd.toFixed(4),
                })
              : t('providerSettings.usageShort', { calls: stats.call_count })}
          </span>
        )}
      </p>
    )
  }

  return (
    <>
      <ProviderKeysSection
        providers={providers}
        refreshing={refreshingCatalogs}
        onChange={setProviders}
        onForceRefresh={() => refreshCatalogs(true)}
      />

      <section className="settings-modal__section">
        <h3 className="settings-modal__section-title">{t('providerSettings.modelsTitle')}</h3>
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
                  {!entry.has_api_key && ` · ${t('providerSettings.noKeyShort')}`}
                </p>
                {renderSummary(entry)}
                {entry.notes && (
                  <p className="settings-modal__hint provider-entry-row__notes" title={entry.notes}>
                    <MessageSquare size={12} /> {entry.notes}
                  </p>
                )}
              </div>

              <label className="provider-card__toggle">
                {t('providerSettings.enabled')}
                <input
                  type="checkbox"
                  checked={entry.enabled}
                  onChange={(event) => void handleToggleEnabled(entry, event.target.checked)}
                  disabled={busyId === entry.id}
                />
              </label>

              <div className="settings-modal__actions">
                <button
                  type="button"
                  className="settings-modal__option settings-modal__option--icon"
                  onClick={() => setEditing(editing !== 'new' && editing?.id === entry.id ? null : entry)}
                  aria-pressed={editing !== 'new' && editing?.id === entry.id}
                  aria-label={t('providerSettings.edit')}
                  title={t('providerSettings.edit')}
                >
                  <Pencil size={14} />
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

            {editing !== 'new' && editing?.id === entry.id && (
              <ProviderEntryForm
                initial={editing}
                providers={providers}
                prices={prices}
                onCancel={() => setEditing(null)}
                onSaved={async () => {
                  setEditing(null)
                  await refresh()
                  await refreshPrices()
                }}
              />
            )}
          </div>
        ))}

        {editing === 'new' && (
          <ProviderEntryForm
            initial={null}
            providers={providers}
            prices={prices}
            onCancel={() => setEditing(null)}
            onSaved={async () => {
              setEditing(null)
              await refresh()
              await refreshPrices()
            }}
          />
        )}
        {editing === null && (
          <div className="settings-modal__actions">
            <button type="button" className="settings-modal__option" onClick={() => setEditing('new')}>
              <Plus size={14} /> {t('providerSettings.addModel')}
            </button>
            <button type="button" className="settings-modal__option" onClick={() => priceImportInputRef.current?.click()}>
              <FileJson size={14} /> {t('modelPricing.importCatalog')}
            </button>
            <input
              ref={priceImportInputRef}
              type="file"
              accept="application/json"
              hidden
              onChange={(event) => {
                const file = event.target.files?.[0]
                event.target.value = ''
                if (file) void handleImportPriceFile(file)
              }}
            />
            <button type="button" className="settings-modal__option" onClick={() => importInputRef.current?.click()}>
              <Upload size={14} /> {t('providerSettings.import')}
            </button>
            <input
              ref={importInputRef}
              type="file"
              accept="application/json"
              hidden
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
        {priceImportMessage && <p className="settings-modal__hint">{priceImportMessage}</p>}
        {editing === null && entries.length > 0 && (
          <p className="settings-modal__hint">{t('providerSettings.exportWarning')}</p>
        )}
      </section>

      <ProviderUsageSection usage={usage} prices={prices} />
    </>
  )
}
