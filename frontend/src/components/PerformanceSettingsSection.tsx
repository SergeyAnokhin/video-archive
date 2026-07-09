import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { PerformanceSettings } from '../types/api'

export function PerformanceSettingsSection() {
  const { t } = useTranslation()
  const [settings, setSettings] = useState<PerformanceSettings | null>(null)

  useEffect(() => {
    void (async () => {
      const res = await fetch('/api/performance-settings')
      if (res.ok) {
        setSettings(await res.json())
      }
    })()
  }, [])

  async function handleWorkersChange(value: number) {
    setSettings((prev) => (prev ? { ...prev, parallel_workers: value } : prev))
    const res = await fetch('/api/performance-settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ parallel_workers: value }),
    })
    if (res.ok) setSettings(await res.json())
  }

  return (
    <section className="settings-modal__section">
      <h3 className="settings-modal__section-title">{t('performanceSettings.title')}</h3>
      <p className="settings-modal__hint">{t('performanceSettings.hint')}</p>

      {settings && (
        <label className="settings-modal__label">
          {t('performanceSettings.parallelWorkers')}
          <input
            className="settings-modal__input"
            type="number"
            min={1}
            max={16}
            value={settings.parallel_workers}
            onChange={(event) => void handleWorkersChange(Number(event.target.value))}
          />
        </label>
      )}
    </section>
  )
}
