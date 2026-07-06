import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { ProviderConfig } from '../types/api'

export function ProviderSettingsSection() {
  const { t } = useTranslation()
  const [providers, setProviders] = useState<ProviderConfig[]>([])
  const [apiKeyDrafts, setApiKeyDrafts] = useState<Record<string, string>>({})
  const [savingProvider, setSavingProvider] = useState<string | null>(null)

  async function refresh() {
    const res = await fetch('/api/settings/providers')
    if (res.ok) {
      const json: { providers: ProviderConfig[] } = await res.json()
      setProviders(json.providers)
    }
  }

  useEffect(() => {
    void refresh()
  }, [])

  async function handleSave(provider: ProviderConfig, changes: Partial<ProviderConfig> & { api_key?: string }) {
    setSavingProvider(provider.provider_name)
    try {
      const body = {
        enabled: provider.enabled,
        vision_model: provider.vision_model,
        text_model: provider.text_model,
        batch_enabled: provider.batch_enabled,
        ...changes,
      }
      const res = await fetch(`/api/settings/providers/${provider.provider_name}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (res.ok) {
        await refresh()
        setApiKeyDrafts((prev) => ({ ...prev, [provider.provider_name]: '' }))
      }
    } finally {
      setSavingProvider(null)
    }
  }

  return (
    <section className="settings-modal__section">
      <h3 className="settings-modal__section-title">{t('providerSettings.title')}</h3>

      {providers.map((provider) => (
        <div key={provider.provider_name} className="conversion-profile-row">
          <div>
            <span className="settings-modal__field-label">{t(`providers.${provider.provider_name}`)}</span>
            <p className="settings-modal__hint">
              {provider.has_api_key ? t('providerSettings.keySet') : t('providerSettings.keyMissing')}
            </p>
          </div>

          <label className="settings-modal__field">
            <span className="settings-modal__field-label">{t('providerSettings.enabled')}</span>
            <input
              type="checkbox"
              checked={provider.enabled}
              onChange={(event) => void handleSave(provider, { enabled: event.target.checked })}
              disabled={savingProvider === provider.provider_name}
            />
          </label>

          <label className="settings-modal__label">
            {t('providerSettings.apiKey')}
            <input
              className="settings-modal__input"
              type="password"
              placeholder={provider.has_api_key ? t('providerSettings.keySetPlaceholder') : ''}
              value={apiKeyDrafts[provider.provider_name] ?? ''}
              onChange={(event) =>
                setApiKeyDrafts((prev) => ({ ...prev, [provider.provider_name]: event.target.value }))
              }
              onBlur={(event) => {
                if (event.target.value) {
                  void handleSave(provider, { api_key: event.target.value })
                }
              }}
            />
          </label>

          <label className="settings-modal__label">
            {t('providerSettings.visionModel')}
            <input
              className="settings-modal__input"
              defaultValue={provider.vision_model ?? ''}
              onBlur={(event) => void handleSave(provider, { vision_model: event.target.value || null })}
            />
          </label>

          <label className="settings-modal__label">
            {t('providerSettings.textModel')}
            <input
              className="settings-modal__input"
              defaultValue={provider.text_model ?? ''}
              onBlur={(event) => void handleSave(provider, { text_model: event.target.value || null })}
            />
          </label>

          <label className="settings-modal__field">
            <span className="settings-modal__field-label">{t('providerSettings.batchEnabled')}</span>
            <input
              type="checkbox"
              checked={provider.batch_enabled}
              onChange={(event) => void handleSave(provider, { batch_enabled: event.target.checked })}
              disabled={savingProvider === provider.provider_name}
            />
          </label>
        </div>
      ))}
    </section>
  )
}
