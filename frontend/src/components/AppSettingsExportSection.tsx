import { Download, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, rawApi } from '../api/client'

interface AppSettingsImportResult {
  tags_upserted: number
  profiles_created: number
  layouts_created: number
  settings_applied: string[]
}

export function AppSettingsExportSection() {
  const { t } = useTranslation()
  const importInputRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  async function handleExport() {
    const res = await rawApi('/api/settings/app-settings/export')
    if (!res.ok) return
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'app-settings-export.json'
    anchor.click()
    URL.revokeObjectURL(url)
  }

  async function handleImportFile(file: File) {
    if (!window.confirm(t('appSettingsExport.importConfirm'))) return
    setBusy(true)
    setMessage(null)
    try {
      const parsed = JSON.parse(await file.text())
      const result = await api<AppSettingsImportResult>('/api/settings/app-settings/import', {
        method: 'POST',
        body: parsed,
      })
      setMessage(
        t('appSettingsExport.importResult', {
          tags: result.tags_upserted,
          profiles: result.profiles_created,
          layouts: result.layouts_created,
        }),
      )
    } catch {
      setMessage(t('appSettingsExport.importError'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="settings-modal__section">
      <h3 className="settings-modal__section-title">{t('appSettingsExport.title')}</h3>
      <p className="settings-modal__hint">{t('appSettingsExport.hint')}</p>
      <div className="settings-modal__actions">
        <button type="button" className="settings-modal__option" onClick={() => void handleExport()}>
          <Download size={14} /> {t('appSettingsExport.export')}
        </button>
        <button
          type="button"
          className="settings-modal__option"
          onClick={() => importInputRef.current?.click()}
          disabled={busy}
        >
          <Upload size={14} /> {t('appSettingsExport.import')}
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
      </div>
      {message && <p className="settings-modal__hint">{message}</p>}
    </section>
  )
}
