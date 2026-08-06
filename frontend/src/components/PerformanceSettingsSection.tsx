import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { tryApi } from '../api/client'
import { useBackendStatus } from '../hooks/useBackendStatus'
import type { HardwareAccelInfo, HardwareDecodeInfo, PerformanceSettings } from '../types/api'

function formatHardwareStatus(info: HardwareAccelInfo | HardwareDecodeInfo | undefined | null): string {
  // Defensive against a backend that hasn't picked up this field yet (e.g.
  // an already-running dev server from before it was added, or a tab left
  // open across a backend redeploy) -- this reads a live network response,
  // not a value this app controls end to end.
  if (!info) return '…'
  return `QSV ${info.qsv ? '✅' : '❌'} · VAAPI ${info.vaapi ? '✅' : '❌'}`
}

export function PerformanceSettingsSection() {
  const { t } = useTranslation()
  const [settings, setSettings] = useState<PerformanceSettings | null>(null)
  const backendStatus = useBackendStatus()

  useEffect(() => {
    void (async () => {
      const loaded = await tryApi<PerformanceSettings>('/api/performance-settings')
      if (loaded) {
        setSettings(loaded)
      }
    })()
  }, [])

  async function updateSettings(patch: Partial<PerformanceSettings>) {
    if (!settings) return
    const merged = { ...settings, ...patch }
    setSettings(merged)
    const saved = await tryApi<PerformanceSettings>('/api/performance-settings', {
      method: 'PUT',
      body: merged,
    })
    if (saved) setSettings(saved)
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
            onChange={(event) => void updateSettings({ parallel_workers: Number(event.target.value) })}
          />
        </label>
      )}

      {settings && (
        <label className="settings-modal__label">
          {t('performanceSettings.convertWorkers')}
          <input
            className="settings-modal__input"
            type="number"
            min={1}
            max={16}
            value={settings.convert_workers}
            onChange={(event) => void updateSettings({ convert_workers: Number(event.target.value) })}
          />
        </label>
      )}
      {settings && <p className="settings-modal__hint">{t('performanceSettings.convertWorkersHint')}</p>}

      {settings && (
        <label className="settings-modal__label">
          {t('performanceSettings.etaWindowMinutes')}
          <input
            className="settings-modal__input"
            type="number"
            min={1}
            max={180}
            value={settings.eta_window_minutes}
            onChange={(event) => void updateSettings({ eta_window_minutes: Number(event.target.value) })}
          />
        </label>
      )}
      {settings && <p className="settings-modal__hint">{t('performanceSettings.etaWindowHint')}</p>}

      {backendStatus.phase === 'ready' && (
        <div className="settings-modal__row">
          <div className="settings-modal__label">
            {t('performanceSettings.hardwareStatusTitle')}
            <p className="settings-modal__hint">
              🚀 {t('performanceSettings.hardwareEncode')}: {formatHardwareStatus(backendStatus.appInfo.hardware_accel)}
            </p>
            <p className="settings-modal__hint">
              🚀 {t('performanceSettings.hardwareDecode')}: {formatHardwareStatus(backendStatus.appInfo.hardware_decode)}
            </p>
            <p className="settings-modal__hint">{t('performanceSettings.hardwareStatusHint')}</p>
          </div>
        </div>
      )}
    </section>
  )
}
