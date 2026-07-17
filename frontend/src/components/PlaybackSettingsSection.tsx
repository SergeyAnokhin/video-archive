import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { tryApi } from '../api/client'
import type { PlaybackMode, PlaybackSettings } from '../types/api'

export function PlaybackSettingsSection() {
  const { t } = useTranslation()
  const [settings, setSettings] = useState<PlaybackSettings | null>(null)

  useEffect(() => {
    void (async () => {
      const loaded = await tryApi<PlaybackSettings>('/api/playback-settings')
      if (loaded) {
        setSettings(loaded)
      }
    })()
  }, [])

  async function handleModeChange(mode: PlaybackMode) {
    setSettings((prev) => (prev ? { ...prev, mode } : prev))
    const saved = await tryApi<PlaybackSettings>('/api/playback-settings', {
      method: 'PUT',
      body: { mode },
    })
    if (saved) {
      setSettings(saved)
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
