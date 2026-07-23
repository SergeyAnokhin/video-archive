import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { tryApi } from '../api/client'
import type { ResourceMonitorSettings } from '../types/api'

export function ResourceMonitorSettingsSection() {
  const { t } = useTranslation()
  const [settings, setSettings] = useState<ResourceMonitorSettings | null>(null)

  useEffect(() => {
    void (async () => {
      const loaded = await tryApi<ResourceMonitorSettings>('/api/resource-monitor-settings')
      if (loaded) {
        setSettings(loaded)
      }
    })()
  }, [])

  async function saveSettings(next: { enabled: boolean; interval_seconds: number }) {
    setSettings((prev) => (prev ? { ...prev, ...next } : prev))
    const saved = await tryApi<ResourceMonitorSettings>('/api/resource-monitor-settings', {
      method: 'PUT',
      body: next,
    })
    if (saved) setSettings(saved)
  }

  return (
    <section className="settings-modal__section">
      <h3 className="settings-modal__section-title">{t('resourceMonitor.title')}</h3>
      <p className="settings-modal__hint">{t('resourceMonitor.hint')}</p>

      {settings && (
        <>
          <label className="settings-modal__label">
            <input
              type="checkbox"
              checked={settings.enabled}
              onChange={(event) =>
                void saveSettings({ enabled: event.target.checked, interval_seconds: settings.interval_seconds })
              }
            />
            {t('resourceMonitor.enabled')}
          </label>

          <label className="settings-modal__label">
            {t('resourceMonitor.intervalSeconds')}
            <input
              className="settings-modal__input"
              type="number"
              min={1}
              max={3600}
              value={settings.interval_seconds}
              onChange={(event) =>
                void saveSettings({ enabled: settings.enabled, interval_seconds: Number(event.target.value) })
              }
            />
          </label>
          <p className="settings-modal__hint">{t('resourceMonitor.intervalHint')}</p>
        </>
      )}
    </section>
  )
}
