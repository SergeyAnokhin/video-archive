import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { tryApi } from '../api/client'
import type { LogRotationSettings } from '../types/api'

export function LogRotationSettingsSection() {
  const { t } = useTranslation()
  const [settings, setSettings] = useState<LogRotationSettings | null>(null)

  useEffect(() => {
    void (async () => {
      const loaded = await tryApi<LogRotationSettings>('/api/log-rotation-settings')
      if (loaded) {
        setSettings(loaded)
      }
    })()
  }, [])

  async function saveSettings(next: { max_bytes: number; backup_count: number }) {
    setSettings((prev) => (prev ? { ...prev, ...next } : prev))
    const saved = await tryApi<LogRotationSettings>('/api/log-rotation-settings', {
      method: 'PUT',
      body: next,
    })
    if (saved) setSettings(saved)
  }

  return (
    <section className="settings-modal__section">
      <h3 className="settings-modal__section-title">{t('logRotation.title')}</h3>
      <p className="settings-modal__hint">{t('logRotation.hint')}</p>

      {settings && (
        <>
          <label className="settings-modal__label">
            {t('logRotation.maxSizeMb')}
            <input
              className="settings-modal__input"
              type="number"
              min={1}
              max={100}
              value={Math.round(settings.max_bytes / (1024 * 1024))}
              onChange={(event) =>
                void saveSettings({
                  max_bytes: Number(event.target.value) * 1024 * 1024,
                  backup_count: settings.backup_count,
                })
              }
            />
          </label>

          <label className="settings-modal__label">
            {t('logRotation.backupCount')}
            <input
              className="settings-modal__input"
              type="number"
              min={1}
              max={20}
              value={settings.backup_count}
              onChange={(event) =>
                void saveSettings({ max_bytes: settings.max_bytes, backup_count: Number(event.target.value) })
              }
            />
          </label>
        </>
      )}
    </section>
  )
}
