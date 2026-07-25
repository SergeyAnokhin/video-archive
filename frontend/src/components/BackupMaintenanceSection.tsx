import { Database, Eraser, FolderTree, RefreshCw, RotateCcw, Save, ScanLine, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useJobs } from '../context/JobsContext'
import { api, tryApi } from '../api/client'
import type { BackupSettings, BackupSummary } from '../types/api'

function postJob(url: string, body?: unknown): Promise<{ id: string }> {
  return api<{ id: string }>(url, { method: 'POST', body })
}

export function BackupMaintenanceSection() {
  const { t } = useTranslation()
  const { jobs, refresh: refreshJobs } = useJobs()
  const [backups, setBackups] = useState<BackupSummary[]>([])
  const [loadingBackups, setLoadingBackups] = useState(true)
  const [settings, setSettings] = useState<BackupSettings | null>(null)
  const [includeSecrets, setIncludeSecrets] = useState(false)
  const [creating, setCreating] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [pendingJobId, setPendingJobId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [maintenanceBusy, setMaintenanceBusy] = useState<string | null>(null)
  const [maintenanceMessage, setMaintenanceMessage] = useState<string | null>(null)

  async function loadBackups() {
    setLoadingBackups(true)
    try {
      const json = await tryApi<{ backups: BackupSummary[] }>('/api/backups')
      if (json) {
        setBackups(json.backups)
      }
    } finally {
      setLoadingBackups(false)
    }
  }

  useEffect(() => {
    void loadBackups()
    void (async () => {
      const loaded = await tryApi<BackupSettings>('/api/backup-settings')
      if (loaded) setSettings(loaded)
    })()
  }, [])

  // Once a backup/restore job started from this section finishes, refresh
  // the list automatically instead of making the user click "Refresh".
  useEffect(() => {
    if (!pendingJobId) return
    const job = jobs.find((j) => j.id === pendingJobId)
    if (job && job.status !== 'queued' && job.status !== 'running') {
      setPendingJobId(null)
      void loadBackups()
    }
  }, [jobs, pendingJobId])

  async function handleCreateBackup() {
    setCreating(true)
    setError(null)
    try {
      const job = await postJob('/api/backups', { include_secrets: includeSecrets })
      setPendingJobId(job.id)
      await refreshJobs()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setCreating(false)
    }
  }

  async function handleRestore(backupId: string) {
    if (!window.confirm(t('backupMaintenance.confirmRestore'))) return
    setBusyId(backupId)
    setError(null)
    try {
      const job = await postJob('/api/backups/restore', { backup_id: backupId })
      setPendingJobId(job.id)
      await refreshJobs()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyId(null)
    }
  }

  async function handleDelete(backupId: string) {
    setBusyId(backupId)
    try {
      await tryApi(`/api/backups/${backupId}`, { method: 'DELETE' })
      await loadBackups()
    } finally {
      setBusyId(null)
    }
  }

  async function handleRetentionChange(value: number) {
    setSettings((prev) => (prev ? { ...prev, retention_count: value } : prev))
    const saved = await tryApi<BackupSettings>('/api/backup-settings', {
      method: 'PUT',
      body: { retention_count: value },
    })
    if (saved) setSettings(saved)
  }

  async function runMaintenance(key: string, url: string, body?: unknown) {
    setMaintenanceBusy(key)
    setMaintenanceMessage(null)
    try {
      await postJob(url, body)
      await refreshJobs()
      setMaintenanceMessage(t('backupMaintenance.actionStarted'))
    } catch (err) {
      setMaintenanceMessage(err instanceof Error ? err.message : String(err))
    } finally {
      setMaintenanceBusy(null)
    }
  }

  return (
    <section className="settings-modal__section">
      <h3 className="settings-modal__section-title">{t('backupMaintenance.title')}</h3>

      {!loadingBackups && backups.length === 0 && (
        <p className="settings-modal__hint">{t('backupMaintenance.empty')}</p>
      )}

      {backups.map((entry) => (
        <div key={entry.id} className="backup-row">
          <div>
            <span className="settings-modal__field-label">
              {new Date(entry.created_at).toLocaleString()}
            </span>
            {entry.includes_secrets && (
              <span className="backup-row__badge">{t('backupMaintenance.includesSecretsBadge')}</span>
            )}
            <p className="settings-modal__hint">
              {t('backupMaintenance.summary', {
                source: entry.source_name,
                size: entry.size_bytes ? `${Math.max(1, Math.ceil(entry.size_bytes / 1024))} KB` : '?',
              })}
            </p>
          </div>
          <div className="settings-modal__actions">
            <button
              type="button"
              className="settings-modal__option settings-modal__option--icon"
              onClick={() => handleRestore(entry.id)}
              disabled={busyId === entry.id}
              aria-label={t('backupMaintenance.restore')}
              title={t('backupMaintenance.restore')}
            >
              <RotateCcw size={14} />
            </button>
            <button
              type="button"
              className="settings-modal__option settings-modal__option--icon"
              onClick={() => handleDelete(entry.id)}
              disabled={busyId === entry.id}
              aria-label={t('backupMaintenance.delete')}
              title={t('backupMaintenance.delete')}
            >
              <Trash2 size={14} />
            </button>
          </div>
        </div>
      ))}

      <label className="settings-modal__field">
        <span className="settings-modal__field-label">{t('backupMaintenance.includeSecrets')}</span>
        <input
          type="checkbox"
          checked={includeSecrets}
          onChange={(event) => setIncludeSecrets(event.target.checked)}
        />
      </label>

      {settings && (
        <label className="settings-modal__label">
          {t('backupMaintenance.retentionCount')}
          <input
            className="settings-modal__input"
            type="number"
            min={1}
            value={settings.retention_count}
            onChange={(event) => void handleRetentionChange(Number(event.target.value))}
          />
        </label>
      )}

      {error && <p className="settings-modal__hint settings-modal__hint--error">{error}</p>}

      <div className="settings-modal__actions">
        <button
          type="button"
          className="settings-modal__option"
          onClick={handleCreateBackup}
          disabled={creating}
        >
          <Save size={14} /> {t('backupMaintenance.createBackup')}
        </button>
        <button
          type="button"
          className="settings-modal__option settings-modal__option--icon"
          onClick={() => void loadBackups()}
          aria-label={t('backupMaintenance.refresh')}
          title={t('backupMaintenance.refresh')}
        >
          <RefreshCw size={14} />
        </button>
      </div>

      <h4 className="settings-modal__section-title">{t('backupMaintenance.maintenanceTitle')}</h4>
      <div className="settings-modal__actions">
        <button
          type="button"
          className="settings-modal__option"
          onClick={() => void runMaintenance('rescan', '/api/jobs/rescan-directory', { path: '' })}
          disabled={maintenanceBusy !== null}
        >
          <ScanLine size={14} /> {t('backupMaintenance.fullRescan')}
        </button>
        <button
          type="button"
          className="settings-modal__option"
          onClick={() => void runMaintenance('cleanup', '/api/jobs/cleanup-stale-records')}
          disabled={maintenanceBusy !== null}
        >
          <Eraser size={14} /> {t('backupMaintenance.cleanupStale')}
        </button>
        <button
          type="button"
          className="settings-modal__option"
          onClick={() => void runMaintenance('optimize', '/api/jobs/optimize-database')}
          disabled={maintenanceBusy !== null}
        >
          <Database size={14} /> {t('backupMaintenance.optimizeDb')}
        </button>
        <button
          type="button"
          className="settings-modal__option"
          onClick={() => void runMaintenance('migrate_previews', '/api/jobs/migrate-legacy-previews')}
          disabled={maintenanceBusy !== null}
        >
          <FolderTree size={14} /> {t('backupMaintenance.migratePreviews')}
        </button>
      </div>
      {maintenanceMessage && <p className="settings-modal__hint">{maintenanceMessage}</p>}
    </section>
  )
}
