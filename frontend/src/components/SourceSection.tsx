import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useJobs } from '../context/JobsContext'
import { useSource } from '../context/SourceContext'
import type { BackupSummary, SourceConfig, SourceProtocol, TestConnectionResult } from '../types/api'

export function SourceSection() {
  const { t } = useTranslation()
  const { source, loading: sourceLoading, setSource } = useSource()
  const { refresh: refreshJobs } = useJobs()
  const [protocol, setProtocol] = useState<SourceProtocol>('local')
  const [name, setName] = useState('')
  const [rootPath, setRootPath] = useState('')
  const [host, setHost] = useState('')
  const [port, setPort] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [testResult, setTestResult] = useState<TestConnectionResult | null>(null)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [confirmingReplace, setConfirmingReplace] = useState(false)
  const [reconnecting, setReconnecting] = useState(false)
  const [reconnectResult, setReconnectResult] = useState<TestConnectionResult | null>(null)
  const [detectedBackups, setDetectedBackups] = useState<BackupSummary[]>([])
  const [restoringId, setRestoringId] = useState<string | null>(null)
  const [restoreMessage, setRestoreMessage] = useState<string | null>(null)

  useEffect(() => {
    if (source) {
      setProtocol(source.protocol === 'smb' ? 'smb' : 'local')
      setName(source.name)
      setRootPath(source.root_path)
      setHost(source.host ?? '')
      setPort(source.port ? String(source.port) : '')
    }
  }, [source])

  function buildPayload() {
    return {
      name,
      protocol,
      root_path: rootPath,
      ...(protocol === 'smb'
        ? {
            host,
            port: port ? Number(port) : undefined,
            username: username || undefined,
            password: password || undefined,
          }
        : {}),
    }
  }

  async function handleTestConnection() {
    setTesting(true)
    setTestResult(null)
    try {
      const res = await fetch('/api/source/test-connection', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildPayload()),
      })
      const json: TestConnectionResult = await res.json()
      setTestResult(json)
    } catch (err) {
      setTestResult({ ok: false, message: err instanceof Error ? err.message : String(err) })
    } finally {
      setTesting(false)
    }
  }

  async function handleSave() {
    if (source && !confirmingReplace) {
      setConfirmingReplace(true)
      return
    }

    setSaving(true)
    setSaveError(null)
    try {
      const res = await fetch('/api/source', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildPayload()),
      })
      if (!res.ok) {
        const json = await res.json().catch(() => null)
        throw new Error(json?.error?.message ?? `HTTP ${res.status}`)
      }
      const json: SourceConfig & { detected_backups: BackupSummary[] } = await res.json()
      setSource(json)
      setConfirmingReplace(false)
      setTestResult(null)
      setPassword('')
      setDetectedBackups(json.detected_backups)
      setRestoreMessage(null)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  async function handleRestoreDetected(backupId: string) {
    if (!window.confirm(t('settings.confirmRestoreDetected'))) return
    setRestoringId(backupId)
    setRestoreMessage(null)
    try {
      const res = await fetch('/api/backups/restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ backup_id: backupId }),
      })
      if (!res.ok) {
        const json = await res.json().catch(() => null)
        throw new Error(json?.detail?.error?.message ?? `HTTP ${res.status}`)
      }
      await refreshJobs()
      setRestoreMessage(t('settings.restoreStarted'))
    } catch (err) {
      setRestoreMessage(err instanceof Error ? err.message : String(err))
    } finally {
      setRestoringId(null)
    }
  }

  async function handleReconnect() {
    setReconnecting(true)
    setReconnectResult(null)
    try {
      const res = await fetch('/api/source/reconnect', { method: 'POST' })
      const json: TestConnectionResult = await res.json()
      setReconnectResult(json)
    } catch (err) {
      setReconnectResult({ ok: false, message: err instanceof Error ? err.message : String(err) })
    } finally {
      setReconnecting(false)
    }
  }

  const isSmb = protocol === 'smb'
  const canSubmit = isSmb ? Boolean(name && host && rootPath) : Boolean(name && rootPath)

  return (
    <section className="settings-modal__section">
      <h3 className="settings-modal__section-title">{t('settings.sourceSection')}</h3>

      {source && (
        <p className="settings-modal__hint">
          {t('settings.currentSource', { name: source.name, path: source.root_path })}
          {' '}
          {source.last_scan_at
            ? t('settings.lastScan', { date: new Date(source.last_scan_at).toLocaleString() })
            : t('settings.neverScanned')}
        </p>
      )}
      {!sourceLoading && !source && (
        <p className="settings-modal__hint">{t('settings.noSourceYet')}</p>
      )}

      <label className="settings-modal__label">
        {t('settings.sourceProtocol')}
        <select
          className="settings-modal__input"
          value={protocol}
          onChange={(event) => setProtocol(event.target.value as SourceProtocol)}
        >
          <option value="local">{t('settings.sourceProtocolLocalOption')}</option>
          <option value="smb">{t('settings.sourceProtocolSmbOption')}</option>
        </select>
      </label>

      <label className="settings-modal__label">
        {t('settings.sourceName')}
        <input
          className="settings-modal__input"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>

      {isSmb && (
        <>
          <label className="settings-modal__label">
            {t('settings.sourceHost')}
            <input
              className="settings-modal__input"
              value={host}
              onChange={(event) => setHost(event.target.value)}
              placeholder="nas.local"
            />
          </label>
          <label className="settings-modal__label">
            {t('settings.sourcePort')}
            <input
              className="settings-modal__input"
              type="number"
              value={port}
              onChange={(event) => setPort(event.target.value)}
              placeholder="445"
            />
          </label>
        </>
      )}

      <label className="settings-modal__label">
        {isSmb ? t('settings.sourceRemotePath') : t('settings.sourcePath')}
        <input
          className="settings-modal__input"
          value={rootPath}
          onChange={(event) => setRootPath(event.target.value)}
          placeholder={isSmb ? 'videos' : './library'}
        />
      </label>

      {isSmb && (
        <>
          <label className="settings-modal__label">
            {t('settings.sourceUsername')}
            <input
              className="settings-modal__input"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
            />
          </label>
          <label className="settings-modal__label">
            {t('settings.sourcePassword')}
            <input
              className="settings-modal__input"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder={source?.protocol === 'smb' ? t('settings.sourcePasswordHint') : ''}
              autoComplete="current-password"
            />
          </label>
        </>
      )}

      {!isSmb && <p className="settings-modal__hint">{t('settings.sourceProtocolLocal')}</p>}

      {testResult && (
        <p
          className={`settings-modal__hint${testResult.ok ? '' : ' settings-modal__hint--error'}`}
        >
          {testResult.ok
            ? t('settings.testOk')
            : t('settings.testFail', { message: testResult.message })}
        </p>
      )}
      {saveError && (
        <p className="settings-modal__hint settings-modal__hint--error">{saveError}</p>
      )}
      {confirmingReplace && (
        <p className="settings-modal__hint settings-modal__hint--warning">
          {t('settings.replaceWarning')}
        </p>
      )}
      {reconnectResult && (
        <p
          className={`settings-modal__hint${reconnectResult.ok ? '' : ' settings-modal__hint--error'}`}
        >
          {reconnectResult.ok
            ? t('settings.reconnectOk')
            : t('settings.testFail', { message: reconnectResult.message })}
        </p>
      )}

      <div className="settings-modal__actions">
        <button
          type="button"
          className="settings-modal__option"
          onClick={handleTestConnection}
          disabled={testing || !canSubmit}
        >
          {t('settings.testConnection')}
        </button>
        <button
          type="button"
          className="settings-modal__option"
          onClick={handleSave}
          disabled={saving || !canSubmit}
        >
          {confirmingReplace ? t('settings.confirmReplace') : t('settings.saveSource')}
        </button>
        {confirmingReplace && (
          <button
            type="button"
            className="settings-modal__option"
            onClick={() => setConfirmingReplace(false)}
          >
            {t('settings.cancel')}
          </button>
        )}
        {source && source.protocol === 'smb' && (
          <button
            type="button"
            className="settings-modal__option"
            onClick={handleReconnect}
            disabled={reconnecting}
          >
            {t('settings.reconnect')}
          </button>
        )}
      </div>

      {detectedBackups.length > 0 && (
        <>
          <p className="settings-modal__hint settings-modal__hint--warning">
            {t('settings.detectedBackupsHint', { count: detectedBackups.length })}
          </p>
          {detectedBackups.map((entry) => (
            <div key={entry.id} className="backup-row">
              <span className="settings-modal__field-label">
                {new Date(entry.created_at).toLocaleString()}
              </span>
              <div className="settings-modal__actions">
                <button
                  type="button"
                  className="settings-modal__option"
                  onClick={() => handleRestoreDetected(entry.id)}
                  disabled={restoringId === entry.id}
                >
                  {t('settings.restoreDetected')}
                </button>
              </div>
            </div>
          ))}
        </>
      )}
      {restoreMessage && <p className="settings-modal__hint">{restoreMessage}</p>}
    </section>
  )
}
