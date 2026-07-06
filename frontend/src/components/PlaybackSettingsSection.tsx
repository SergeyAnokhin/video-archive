import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { PlaybackMode, PlaybackSettings } from '../types/api'

export function PlaybackSettingsSection() {
  const { t } = useTranslation()
  const [settings, setSettings] = useState<PlaybackSettings | null>(null)

  useEffect(() => {
    void (async () => {
      const res = await fetch('/api/playback-settings')
      if (res.ok) {
        setSettings(await res.json())
      }
    })()
  }, [])

  async function handleModeChange(mode: PlaybackMode) {
    setSettings((prev) => (prev ? { ...prev, mode } : prev))
    const res = await fetch('/api/playback-settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode }),
    })
    if (res.ok) {
      setSettings(await res.json())
    }
  }

  return (
    <section className="settings-modal__section">
      <h3 className="settings-modal__section-title">{t('playbackSettings.title')}</h3>
      <p className="settings-modal__hint">{t('playbackSettings.hint')}</p>

      {settings && (
        <label className="settings-modal__label">
          {t('playbackSettings.mode')}
          <select
            className="settings-modal__input"
            value={settings.mode}
            onChange={(event) => void handleModeChange(event.target.value as PlaybackMode)}
          >
            <option value="stream">{t('playbackSettings.modeStream')}</option>
            <option value="direct_link">{t('playbackSettings.modeDirectLink')}</option>
          </select>
        </label>
      )}
    </section>
  )
}
