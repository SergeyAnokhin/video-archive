import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { tryApi } from '../api/client'
import type { BackendHealthSettings } from '../types/api'

type TimeoutField = 'slow_timeout_seconds' | 'offline_timeout_seconds'

/** Settings -> Network block for the top-bar status dot's slow/offline
 * timeouts (chat request 2026-07-19 follow-up: "let me configure these").
 * Both fields always ship together in one PUT -- sending just the changed
 * one would let the backend's per-field `Field(default=...)` silently reset
 * the other back to its default on an omitted key. */
export function BackendHealthSettingsSection() {
  const { t } = useTranslation()
  const [settings, setSettings] = useState<BackendHealthSettings | null>(null)

  useEffect(() => {
    void (async () => {
      const loaded = await tryApi<BackendHealthSettings>('/api/backend-health-settings')
      if (loaded) setSettings(loaded)
    })()
  }, [])

  async function handleChange(field: TimeoutField, value: number) {
    if (!settings) return
    const next = { ...settings, [field]: value }
    setSettings(next)
    const saved = await tryApi<BackendHealthSettings>('/api/backend-health-settings', {
      method: 'PUT',
      body: {
        slow_timeout_seconds: next.slow_timeout_seconds,
        offline_timeout_seconds: next.offline_timeout_seconds,
      },
    })
    if (saved) setSettings(saved)
  }

  return (
    <section className="settings-modal__section">
      <h3 className="settings-modal__section-title">{t('backendHealthSettings.title')}</h3>
      <p className="settings-modal__hint">{t('backendHealthSettings.hint')}</p>

      {settings && (
        <>
          <label className="settings-modal__label">
            {t('backendHealthSettings.slowTimeout')}
            <input
              className="settings-modal__input"
              type="number"
              min={1}
              max={30}
              value={settings.slow_timeout_seconds}
              onChange={(event) => void handleChange('slow_timeout_seconds', Number(event.target.value))}
            />
          </label>
          <label className="settings-modal__label">
            {t('backendHealthSettings.offlineTimeout')}
            <input
              className="settings-modal__input"
              type="number"
              min={1}
              max={60}
              value={settings.offline_timeout_seconds}
              onChange={(event) => void handleChange('offline_timeout_seconds', Number(event.target.value))}
            />
          </label>
        </>
      )}
    </section>
  )
}
