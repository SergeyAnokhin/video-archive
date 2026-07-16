import { Download, GripVertical, Pencil, Plus, RefreshCw, Save, Settings, Trash2, Upload, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { ModelPricing, ProviderEntry, ProviderType, ProviderUsageSummary } from '../types/api'

const PROVIDER_TYPES: ProviderType[] = ['openrouter', 'gemini', 'mistral', 'fal']
const MODEL_LISTING_SUPPORTED: ProviderType[] = ['openrouter', 'gemini', 'mistral']
// Mirrors the backend's batch-capable provider set (`registry.entry_supports_batch`).
const BATCH_SUPPORTED: ProviderType[] = ['gemini', 'mistral']

type FormValue = ProviderEntry | 'new' | null

export function ProviderSettingsSection() {
  const { t } = useTranslation()
  const [entries, setEntries] = useState<ProviderEntry[]>([])
  const [editing, setEditing] = useState<FormValue>(null)
  const [advancedId, setAdvancedId] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null)
  const importInputRef = useRef<HTMLInputElement>(null)

  async function refresh() {
    const res = await fetch('/api/settings/provider-entries')
    if (res.ok) {
      const json: { entries: ProviderEntry[] } = await res.json()
      setEntries(json.entries)
    }
  }

  useEffect(() => {
    void refresh()
  }, [])

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
      const res = await fetch(`/api/settings/provider-entries/${entry.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (res.ok) await refresh()
    } finally {
      setBusyId(null)
    }
  }

  async function handleDelete(entry: ProviderEntry) {
    if (!window.confirm(t('providerSettings.confirmDelete'))) return
    setBusyId(entry.id)
    try {
      await fetch(`/api/settings/provider-entries/${entry.id}`, { method: 'DELETE' })
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
    await fetch('/api/settings/provider-entries/reorder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ordered_ids: reordered.map((entry) => entry.id) }),
    })
    await refresh()
  }

  async function handleExport() {
    if (!window.confirm(t('providerSettings.exportConfirm'))) return
    const res = await fetch('/api/settings/provider-entries/export')
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
      const res = await fetch('/api/settings/provider-entries/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entries: parsed.entries ?? [] }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json: { entries: ProviderEntry[]; skipped: number } = await res.json()
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
                onClick={() => setAdvancedId(advancedId === entry.id ? null : entry.id)}
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
              <label className="settings-modal__label">
                {t('providerSettings.textModel')}
                <input
                  className="settings-modal__input"
                  defaultValue={entry.text_model ?? ''}
                  onBlur={(event) => void handleUpdate(entry, { text_model: event.target.value || null })}
                />
              </label>
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
            </div>
          )}
        </div>
      ))}

      {editing === null ? (
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
      ) : (
        <ProviderEntryForm
          initial={editing === 'new' ? null : editing}
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
    <ModelPricingSection />
    <ProviderUsageSection />
    </>
  )
}

function ModelPricingSection() {
  const { t } = useTranslation()
  const [prices, setPrices] = useState<ModelPricing[]>([])
  const [refreshing, setRefreshing] = useState(false)
  const [refreshResult, setRefreshResult] = useState<{ updated: string[]; not_found: string[] } | null>(null)

  async function refresh() {
    const res = await fetch('/api/settings/model-pricing')
    if (res.ok) {
      const json: { prices: ModelPricing[] } = await res.json()
      setPrices(json.prices)
    }
  }

  useEffect(() => {
    void refresh()
  }, [])

  async function handleSavePrice(row: ModelPricing, changes: { input_per_million?: number; output_per_million?: number }) {
    const body = {
      provider_type: row.provider_type,
      model_name: row.model_name,
      input_per_million: row.input_per_million ?? 0,
      output_per_million: row.output_per_million ?? 0,
      ...changes,
    }
    const res = await fetch('/api/settings/model-pricing', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (res.ok) await refresh()
  }

  async function handleRefreshOpenRouter() {
    setRefreshing(true)
    setRefreshResult(null)
    try {
      const res = await fetch('/api/settings/model-pricing/refresh-openrouter', { method: 'POST' })
      const json = await res.json().catch(() => null)
      if (res.ok && json) {
        setRefreshResult(json)
        await refresh()
      }
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <section className="settings-modal__section">
      <h3 className="settings-modal__section-title">{t('modelPricing.title')}</h3>
      <p className="settings-modal__hint">{t('modelPricing.hint')}</p>
      <div className="settings-modal__actions">
        <button type="button" className="settings-modal__option" onClick={() => void handleRefreshOpenRouter()} disabled={refreshing}>
          <RefreshCw size={14} /> {refreshing ? t('modelPricing.refreshing') : t('modelPricing.refreshOpenRouter')}
        </button>
      </div>
      {refreshResult && (
        <p className="settings-modal__hint">
          {t('modelPricing.refreshResult', { updated: refreshResult.updated.length, notFound: refreshResult.not_found.length })}
        </p>
      )}
      {prices.length === 0 ? (
        <p className="settings-modal__hint">{t('modelPricing.empty')}</p>
      ) : (
        <div className="provider-usage-table__wrap">
          <table className="provider-usage-table">
            <thead>
              <tr>
                <th>{t('modelPricing.colModel')}</th>
                <th>{t('modelPricing.colInput')}</th>
                <th>{t('modelPricing.colOutput')}</th>
                <th>{t('modelPricing.colSource')}</th>
                <th>{t('modelPricing.colUpdatedAt')}</th>
              </tr>
            </thead>
            <tbody>
              {prices.map((row) => (
                <tr key={`${row.provider_type}-${row.model_name}`}>
                  <td>
                    {t(`providers.${row.provider_type}`)} / {row.model_name}
                  </td>
                  <td>
                    <input
                      type="number"
                      step="any"
                      className="settings-modal__input"
                      defaultValue={row.input_per_million ?? ''}
                      onBlur={(event) => {
                        const value = Number.parseFloat(event.target.value)
                        if (!Number.isNaN(value)) void handleSavePrice(row, { input_per_million: value })
                      }}
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      step="any"
                      className="settings-modal__input"
                      defaultValue={row.output_per_million ?? ''}
                      onBlur={(event) => {
                        const value = Number.parseFloat(event.target.value)
                        if (!Number.isNaN(value)) void handleSavePrice(row, { output_per_million: value })
                      }}
                    />
                  </td>
                  <td>{t(`modelPricing.source.${row.source}`)}</td>
                  <td>{new Date(row.updated_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function ProviderUsageSection() {
  const { t } = useTranslation()
  const [usage, setUsage] = useState<ProviderUsageSummary[]>([])

  useEffect(() => {
    let cancelled = false
    fetch('/api/settings/provider-usage')
      .then((res) => (res.ok ? res.json() : null))
      .then((json: { usage: ProviderUsageSummary[] } | null) => {
        if (!cancelled) setUsage(json?.usage ?? [])
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <section className="settings-modal__section">
      <h3 className="settings-modal__section-title">{t('providerUsage.title')}</h3>
      <p className="settings-modal__hint">{t('providerUsage.hint')}</p>
      {usage.length === 0 ? (
        <p className="settings-modal__hint">{t('providerUsage.empty')}</p>
      ) : (
        <div className="provider-usage-table__wrap">
          <table className="provider-usage-table">
            <thead>
              <tr>
                <th>{t('providerUsage.colModel')}</th>
                <th>{t('providerUsage.colCalls')}</th>
                <th>{t('providerUsage.colTokensIn')}</th>
                <th>{t('providerUsage.colTokensOut')}</th>
                <th>{t('providerUsage.colCost')}</th>
                <th>{t('providerUsage.colLastUsed')}</th>
              </tr>
            </thead>
            <tbody>
              {usage.map((row) => (
                <tr key={`${row.provider_type}-${row.model_name}`}>
                  <td>
                    {t(`providers.${row.provider_type}`)} / {row.model_name ?? t('providerUsage.notAvailable')}
                  </td>
                  <td>{t('providerUsage.callsValue', { success: row.success_count, total: row.call_count })}</td>
                  <td>{row.total_tokens_in ?? t('providerUsage.notAvailable')}</td>
                  <td>{row.total_tokens_out ?? t('providerUsage.notAvailable')}</td>
                  <td>
                    {row.total_estimated_cost_usd != null
                      ? `$${row.total_estimated_cost_usd.toFixed(4)}`
                      : t('providerUsage.notAvailable')}
                  </td>
                  <td>{new Date(row.last_used_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

interface ProviderEntryFormProps {
  initial: ProviderEntry | null
  onCancel: () => void
  onSaved: () => Promise<void>
}

function ProviderEntryForm({ initial, onCancel, onSaved }: ProviderEntryFormProps) {
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
      const res = editingExisting
        ? await fetch(`/api/settings/provider-entries/${initial.id}/models`, { method: 'POST' })
        : await fetch('/api/settings/provider-entries/models', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider_type: providerType, api_key: apiKey }),
          })
      const json = await res.json().catch(() => null)
      if (!res.ok) {
        throw new Error(json?.detail?.error?.message ?? `HTTP ${res.status}`)
      }
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
      const res = await fetch(url, {
        method: editingExisting ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const json = await res.json().catch(() => null)
        throw new Error(json?.detail?.error?.message ?? `HTTP ${res.status}`)
      }
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
            {modelOptions.map((model) => (
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
          has no discoverable model catalog to list -- see providers/fal.py). */}
      {!MODEL_LISTING_SUPPORTED.includes(providerType) && (
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
