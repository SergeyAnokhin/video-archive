import { KeyRound, RefreshCw, Save, Trash2, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { tryApi } from '../api/client'
import type { ProviderStatus, ProviderType } from '../types/api'

type ProvidersResponse = { providers: ProviderStatus[] }

// One row per provider type: its single shared API key (write-only -- only
// presence and a masked suffix come back) and the state of its cached model
// catalog. The catalog refreshes itself at most once a day (see
// `backend/app/provider_catalog.py`); "Refresh now" forces it.
export function ProviderKeysSection({
  providers,
  refreshing,
  onChange,
  onForceRefresh,
}: {
  providers: ProviderStatus[]
  refreshing: boolean
  onChange: (providers: ProviderStatus[]) => void
  onForceRefresh: () => Promise<void>
}) {
  const { t } = useTranslation()
  const [editingType, setEditingType] = useState<ProviderType | null>(null)
  const [keyDraft, setKeyDraft] = useState('')
  const [busyType, setBusyType] = useState<ProviderType | null>(null)

  async function run(providerType: ProviderType, request: () => Promise<ProvidersResponse | null>) {
    setBusyType(providerType)
    try {
      const json = await request()
      if (json) onChange(json.providers)
      return json !== null
    } finally {
      setBusyType(null)
    }
  }

  async function handleSaveKey(providerType: ProviderType) {
    if (!keyDraft.trim()) return
    const saved = await run(providerType, () =>
      tryApi<ProvidersResponse>(`/api/settings/providers/${providerType}/api-key`, { method: 'PUT', body: { api_key: keyDraft.trim() } }),
    )
    if (saved) {
      setEditingType(null)
      setKeyDraft('')
    }
  }

  async function handleDeleteKey(providerType: ProviderType) {
    if (!window.confirm(t('providerKeys.confirmDeleteKey', { provider: t(`providers.${providerType}`) }))) return
    await run(providerType, () => tryApi<ProvidersResponse>(`/api/settings/providers/${providerType}/api-key`, { method: 'DELETE' }))
  }

  async function handleDeleteLegacyKeys(providerType: ProviderType) {
    if (!window.confirm(t('providerKeys.confirmDeleteLegacy'))) return
    await run(providerType, () => tryApi<ProvidersResponse>(`/api/settings/providers/${providerType}/legacy-keys`, { method: 'DELETE' }))
  }

  function catalogLine(provider: ProviderStatus): string {
    if (!provider.catalog_supported) return t('providerKeys.catalogNotSupported')
    if (!provider.has_api_key) return t('providerKeys.catalogNeedsKey')
    if (!provider.fetched_at) return t('providerKeys.catalogNotLoaded')
    return t('providerKeys.catalogLine', {
      count: provider.catalog_count,
      date: new Date(provider.fetched_at).toLocaleString(),
    })
  }

  return (
    <section className="settings-modal__section">
      <h3 className="settings-modal__section-title">{t('providerKeys.title')}</h3>
      <p className="settings-modal__hint">{t('providerKeys.hint')}</p>

      {providers.map((provider) => {
        const type = provider.provider_type
        const busy = busyType === type
        return (
          <div key={type} className="provider-key-row">
            <div className="provider-entry-row__main">
              <div className="provider-entry-row__info">
                <span className="settings-modal__field-label">{t(`providers.${type}`)}</span>
                <p className="settings-modal__hint">
                  {provider.has_api_key
                    ? t('providerKeys.keySet', { suffix: provider.key_suffix })
                    : t('providerKeys.keyMissing')}
                  {' · '}
                  {catalogLine(provider)}
                </p>
                {provider.error && (
                  <p className="settings-modal__hint settings-modal__hint--error">
                    {t('providerKeys.catalogError', { error: provider.error })}
                  </p>
                )}
                {provider.legacy_key_conflict && (
                  <p className="settings-modal__hint settings-modal__hint--warning">
                    {t('providerKeys.legacyConflict')}{' '}
                    <button
                      type="button"
                      className="settings-modal__link-button"
                      onClick={() => void handleDeleteLegacyKeys(type)}
                      disabled={busy}
                    >
                      {t('providerKeys.deleteLegacy')}
                    </button>
                  </p>
                )}
              </div>
              <div className="settings-modal__actions">
                <button
                  type="button"
                  className="settings-modal__option"
                  onClick={() => {
                    setKeyDraft('')
                    setEditingType(editingType === type ? null : type)
                  }}
                  aria-pressed={editingType === type}
                >
                  <KeyRound size={14} /> {provider.has_api_key ? t('providerKeys.changeKey') : t('providerKeys.setKey')}
                </button>
                {provider.has_api_key && (
                  <button
                    type="button"
                    className="settings-modal__option settings-modal__option--icon"
                    onClick={() => void handleDeleteKey(type)}
                    disabled={busy}
                    aria-label={t('providerKeys.deleteKey')}
                    title={t('providerKeys.deleteKey')}
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
            </div>
            {editingType === type && (
              <div className="settings-modal__row provider-key-row__editor">
                <label className="settings-modal__label">
                  {t('providerSettings.apiKey')}
                  <input
                    className="settings-modal__input"
                    type="password"
                    autoComplete="off"
                    value={keyDraft}
                    autoFocus
                    onChange={(event) => setKeyDraft(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') void handleSaveKey(type)
                    }}
                  />
                </label>
                <button
                  type="button"
                  className="settings-modal__option"
                  onClick={() => void handleSaveKey(type)}
                  disabled={busy || !keyDraft.trim()}
                >
                  <Save size={14} /> {busy ? t('providerKeys.checking') : t('providerSettings.save')}
                </button>
                <button type="button" className="settings-modal__option" onClick={() => setEditingType(null)}>
                  <X size={14} /> {t('providerSettings.cancel')}
                </button>
              </div>
            )}
          </div>
        )
      })}

      <div className="settings-modal__actions">
        <button
          type="button"
          className="settings-modal__option"
          onClick={() => void onForceRefresh()}
          disabled={refreshing}
        >
          <RefreshCw size={14} /> {refreshing ? t('providerKeys.refreshing') : t('providerKeys.refreshNow')}
        </button>
      </div>
    </section>
  )
}
