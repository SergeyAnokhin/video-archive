import { ImageOff, Trash2, Repeat } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useJobs } from '../context/JobsContext'
import { useSource } from '../context/SourceContext'
import { api, tryApi } from '../api/client'
import type { SavedSource, SourceConfig } from '../types/api'

function formatSize(bytes: number): string {
  if (bytes <= 0) return '0 KB'
  return `${Math.max(1, Math.ceil(bytes / 1024))} KB`
}

export function SavedSourcesSection() {
  const { t } = useTranslation()
  const { setSource } = useSource()
  const { refresh: refreshJobs } = useJobs()
  const [sources, setSources] = useState<SavedSource[]>([])
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function loadSources() {
    setLoading(true)
    try {
      const json = await tryApi<{ sources: SavedSource[] }>('/api/sources')
      if (json) {
        setSources(json.sources)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadSources()
  }, [])

  async function handleActivate(sourceId: string) {
    setBusyId(sourceId)
    setError(null)
    try {
      const json = await api<SourceConfig>(`/api/sources/${sourceId}/activate`, { method: 'POST' })
      setSource(json)
      await refreshJobs()
      await loadSources()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyId(null)
    }
  }

  async function handleClearCache(sourceId: string) {
    if (!window.confirm(t('savedSources.confirmClearCache'))) return
    setBusyId(sourceId)
    setError(null)
    try {
      await api(`/api/sources/${sourceId}/preview-cache`, { method: 'DELETE' })
      await loadSources()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyId(null)
    }
  }

  async function handleForget(sourceId: string) {
    if (!window.confirm(t('savedSources.confirmForget'))) return
    setBusyId(sourceId)
    setError(null)
    try {
      await api(`/api/sources/${sourceId}`, { method: 'DELETE' })
      await loadSources()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <section className="settings-modal__section">
      <h3 className="settings-modal__section-title">{t('savedSources.title')}</h3>
      <p className="settings-modal__hint">{t('savedSources.hint')}</p>

      {!loading && sources.length === 0 && (
        <p className="settings-modal__hint">{t('savedSources.empty')}</p>
      )}

      {sources.map((entry) => (
        <div key={entry.id} className="backup-row">
          <div>
            <span className="settings-modal__field-label">{entry.name}</span>
            {entry.is_active && <span className="backup-row__badge">{t('savedSources.active')}</span>}
            <p className="settings-modal__hint">
              {entry.protocol === 'smb' ? `${entry.host}/${entry.root_path}` : entry.root_path}
            </p>
            <p className="settings-modal__hint">
              {t('savedSources.cacheSummary', {
                size: formatSize(entry.preview_cache.size_bytes),
                count: entry.preview_cache.file_count,
              })}
            </p>
          </div>
          <div className="settings-modal__actions">
            {!entry.is_active && (
              <button
                type="button"
                className="settings-modal__option settings-modal__option--icon"
                onClick={() => handleActivate(entry.id)}
                disabled={busyId === entry.id}
                aria-label={t('savedSources.activate')}
                title={t('savedSources.activate')}
              >
                <Repeat size={14} />
              </button>
            )}
            <button
              type="button"
              className="settings-modal__option settings-modal__option--icon"
              onClick={() => handleClearCache(entry.id)}
              disabled={busyId === entry.id || entry.preview_cache.file_count === 0}
              aria-label={t('savedSources.clearCache')}
              title={t('savedSources.clearCache')}
            >
              <ImageOff size={14} />
            </button>
            <button
              type="button"
              className="settings-modal__option settings-modal__option--icon"
              onClick={() => handleForget(entry.id)}
              disabled={busyId === entry.id || entry.is_active}
              aria-label={entry.is_active ? t('savedSources.cannotForgetActive') : t('savedSources.forget')}
              title={entry.is_active ? t('savedSources.cannotForgetActive') : t('savedSources.forget')}
            >
              <Trash2 size={14} />
            </button>
          </div>
        </div>
      ))}

      {error && <p className="settings-modal__hint settings-modal__hint--error">{error}</p>}
    </section>
  )
}
