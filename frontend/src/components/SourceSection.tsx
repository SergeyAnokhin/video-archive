import { Lock, Plug, RefreshCw, RotateCcw, Save, Unlock, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useJobs } from '../context/JobsContext'
import { useSource } from '../context/SourceContext'
import { api, rawApi, tryApi } from '../api/client'
import { useBackendStatus } from '../hooks/useBackendStatus'
import { formatElapsedCompact, type DurationUnitLabels } from '../utils/format'
import type {
  BackupSummary,
  SmbLockStatus,
  SourceConfig,
  SourceProtocol,
  SourceStatus,
  TestConnectionResult,
} from '../types/api'

const SMB_LOCK_POLL_INTERVAL_MS = 5000

export function SourceSection() {
  const { t } = useTranslation()
  const { source, loading: sourceLoading, setSource } = useSource()
  const { refresh: refreshJobs } = useJobs()
  const backendStatus = useBackendStatus()
  const isWindows = backendStatus.phase === 'ready' ? (backendStatus.appInfo.platform?.windows ?? false) : false
  const [protocol, setProtocol] = useState<SourceProtocol>('local')
  const [name, setName] = useState('')
  const [rootPath, setRootPath] = useState('')
  const [host, setHost] = useState('')
  const [port, setPort] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [directAccessEnabled, setDirectAccessEnabled] = useState(false)
  const [verifySsl, setVerifySsl] = useState(true)
  const [testResult, setTestResult] = useState<TestConnectionResult | null>(null)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [confirmingReplace, setConfirmingReplace] = useState(false)
  const [reconnecting, setReconnecting] = useState(false)
  const [reconnectResult, setReconnectResult] = useState<SourceStatus | null>(null)
  const [status, setStatus] = useState<SourceStatus | null>(null)
  const [lockStatus, setLockStatus] = useState<SmbLockStatus | null>(null)
  const [releasingLock, setReleasingLock] = useState(false)
  const [detectedBackups, setDetectedBackups] = useState<BackupSummary[]>([])
  const [restoringId, setRestoringId] = useState<string | null>(null)
  const [restoreMessage, setRestoreMessage] = useState<string | null>(null)

  useEffect(() => {
    if (source) {
      setProtocol(source.protocol === 'smb' || source.protocol === 'webdav' ? source.protocol : 'local')
      setName(source.name)
      setRootPath(source.root_path)
      setHost(source.host ?? '')
      setPort(source.port ? String(source.port) : '')
      setDirectAccessEnabled(source.direct_access_enabled)
      setVerifySsl(source.verify_ssl)
    }
  }, [source])

  // Passive connection status (real-time, not just the saved
  // `direct_access_enabled` flag) -- re-fetched whenever the active source
  // itself changes; `handleSave`/`handleReconnect` additionally push a fresh
  // result after they touch the connection (e.g. an in-place host/port edit
  // keeps the same source id, so it wouldn't otherwise re-trigger this).
  useEffect(() => {
    let cancelled = false
    if (source && source.protocol !== 'local') {
      void tryApi<SourceStatus>('/api/source/status').then((json) => {
        if (!cancelled) setStatus(json)
      })
    } else {
      setStatus(null)
    }
    return () => {
      cancelled = true
    }
  }, [source?.id, source?.protocol])

  // The SMB serialization lock is process-wide, not tied to a source id, so
  // this polls independently of `source?.id` -- but only while an SMB source
  // is active, since that's the only time it can ever be held. Polled
  // (rather than fetched once) so the indicator reflects a lock taken or
  // released by any in-flight job, not just this component's own actions.
  useEffect(() => {
    if (source?.protocol !== 'smb') {
      setLockStatus(null)
      return
    }
    let cancelled = false
    async function poll() {
      const json = await tryApi<SmbLockStatus>('/api/source/smb-lock-status')
      if (json && !cancelled) setLockStatus(json)
    }
    void poll()
    const timer = window.setInterval(() => void poll(), SMB_LOCK_POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [source?.protocol])

  async function handleReleaseLock() {
    setReleasingLock(true)
    try {
      const json = await api<SmbLockStatus>('/api/source/smb-lock-status/release', { method: 'POST' })
      setLockStatus(json)
    } finally {
      setReleasingLock(false)
    }
  }

  function buildPayload() {
    return {
      name,
      protocol,
      root_path: rootPath,
      ...(protocol === 'smb' || protocol === 'webdav'
        ? {
            host,
            port: port ? Number(port) : undefined,
            username: username || undefined,
            password: password || undefined,
            direct_access_enabled: protocol === 'smb' && directAccessEnabled,
            verify_ssl: protocol !== 'webdav' || verifySsl,
          }
        : {}),
    }
  }

  async function handleTestConnection() {
    setTesting(true)
    setTestResult(null)
    try {
      const res = await rawApi('/api/source/test-connection', { method: 'POST', body: buildPayload() })
      const json: TestConnectionResult = await res.json()
      setTestResult(json)
    } catch (err) {
      setTestResult({ ok: false, message: err instanceof Error ? err.message : String(err) })
    } finally {
      setTesting(false)
    }
  }

  async function handleSave() {
    if (source && !confirmingReplace && !isConnectionOnlyEdit) {
      setConfirmingReplace(true)
      return
    }

    setSaving(true)
    setSaveError(null)
    try {
      const json = await api<SourceConfig & { detected_backups: BackupSummary[] }>('/api/source', {
        method: 'PUT',
        body: buildPayload(),
      })
      setSource(json)
      setConfirmingReplace(false)
      setTestResult(null)
      setPassword('')
      setDetectedBackups(json.detected_backups)
      setRestoreMessage(null)
      await refreshJobs()
      if (json.protocol !== 'local') {
        setStatus(await tryApi<SourceStatus>('/api/source/status'))
      }
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
      await api('/api/backups/restore', {
        method: 'POST',
        body: { backup_id: backupId },
      })
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
      const res = await rawApi('/api/source/reconnect', { method: 'POST' })
      const json: SourceStatus = await res.json()
      setReconnectResult(json)
      setStatus(json)
    } catch (err) {
      setReconnectResult({
        ok: false,
        message: err instanceof Error ? err.message : String(err),
        direct_access_enabled: false,
        direct_access_active: null,
      })
    } finally {
      setReconnecting(false)
    }
  }

  const isSmb = protocol === 'smb'
  const isWebdav = protocol === 'webdav'
  const isRemote = isSmb || isWebdav
  const canSubmit = isRemote ? Boolean(name && host && rootPath) : Boolean(name && rootPath)
  // Reconnecting the active source with different connection parameters
  // (host/port/credentials/direct access/verify_ssl/name) rather than
  // switching to a different one -- same underlying data (protocol +
  // root_path unchanged), so no replace confirmation and no backup/rescan
  // (mirrors the backend's own `is_reconnect` check in `put_source()`).
  const isConnectionOnlyEdit =
    source !== null &&
    source.protocol !== 'local' &&
    source.protocol === protocol &&
    isRemote &&
    rootPath.replace(/^[/\\]+/, '').replace(/[/\\]+$/, '') === source.root_path

  let statusHint: { text: string; variant: 'error' | 'warning' | null } | null = null
  if (source?.protocol !== 'local' && status) {
    if (!status.ok) {
      statusHint = { text: t('settings.sourceStatusFail', { message: status.message }), variant: 'error' }
    } else if (status.direct_access_enabled) {
      statusHint = status.direct_access_active
        ? { text: t('settings.sourceStatusDirectActive'), variant: null }
        : { text: t('settings.sourceStatusDirectFallback'), variant: 'warning' }
    }
  }

  const durationUnits: DurationUnitLabels = {
    day: t('jobs.unitShort.day'),
    hour: t('jobs.unitShort.hour'),
    minute: t('jobs.unitShort.minute'),
    second: t('jobs.unitShort.second'),
  }

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
      {statusHint && (
        <p
          className={`settings-modal__hint${statusHint.variant ? ` settings-modal__hint--${statusHint.variant}` : ''}`}
        >
          {statusHint.text}
        </p>
      )}

      {source?.protocol === 'smb' && lockStatus && (
        <p
          className={`settings-modal__hint settings-modal__hint--smb-lock${lockStatus.held ? ' settings-modal__hint--warning' : ''}`}
        >
          {lockStatus.held ? <Lock size={13} /> : <Unlock size={13} />}
          {lockStatus.held
            ? t('settings.sourceSmbLockHeld', {
                duration: formatElapsedCompact(lockStatus.seconds_held ?? 0, durationUnits),
              })
            : t('settings.sourceSmbLockFree')}
          {lockStatus.held && (
            <button
              type="button"
              className="settings-modal__option"
              onClick={() => void handleReleaseLock()}
              disabled={releasingLock}
            >
              <Unlock size={13} /> {t('settings.sourceSmbLockRelease')}
            </button>
          )}
        </p>
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
          <option value="webdav">{t('settings.sourceProtocolWebdavOption')}</option>
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

      {isRemote && (
        <>
          <label className="settings-modal__label">
            {t('settings.sourceHost')}
            <input
              className="settings-modal__input"
              value={host}
              onChange={(event) => setHost(event.target.value)}
              placeholder={isWebdav ? 'https://nas.local' : 'nas.local'}
            />
          </label>
          <label className="settings-modal__label">
            {t('settings.sourcePort')}
            <input
              className="settings-modal__input"
              type="number"
              value={port}
              onChange={(event) => setPort(event.target.value)}
              placeholder={isWebdav ? '5006' : '445'}
            />
          </label>
        </>
      )}

      <label className="settings-modal__label">
        {isRemote ? t('settings.sourceRemotePath') : t('settings.sourcePath')}
        <input
          className="settings-modal__input"
          value={rootPath}
          onChange={(event) => setRootPath(event.target.value)}
          placeholder={isRemote ? 'videos' : './library'}
        />
      </label>

      {isRemote && (
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
              placeholder={source?.protocol !== 'local' ? t('settings.sourcePasswordHint') : ''}
              autoComplete="current-password"
            />
          </label>
          {isSmb && isWindows && (
            <label className="settings-modal__field">
              <span className="settings-modal__field-label">{t('settings.sourceDirectAccess')}</span>
              <input
                type="checkbox"
                checked={directAccessEnabled}
                onChange={(event) => setDirectAccessEnabled(event.target.checked)}
              />
            </label>
          )}
          {isWebdav && (
            <label className="settings-modal__field">
              <span className="settings-modal__field-label">{t('settings.sourceVerifySsl')}</span>
              <input
                type="checkbox"
                checked={verifySsl}
                onChange={(event) => setVerifySsl(event.target.checked)}
              />
            </label>
          )}
          {isWebdav && !verifySsl && (
            <p className="settings-modal__hint settings-modal__hint--warning">
              {t('settings.sourceVerifySslWarning')}
            </p>
          )}
        </>
      )}

      {!isRemote && <p className="settings-modal__hint">{t('settings.sourceProtocolLocal')}</p>}

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
          <Plug size={14} /> {t('settings.testConnection')}
        </button>
        <button
          type="button"
          className="settings-modal__option"
          onClick={handleSave}
          disabled={saving || !canSubmit}
        >
          <Save size={14} /> {confirmingReplace ? t('settings.confirmReplace') : t('settings.saveSource')}
        </button>
        {confirmingReplace && (
          <button
            type="button"
            className="settings-modal__option"
            onClick={() => setConfirmingReplace(false)}
          >
            <X size={14} /> {t('settings.cancel')}
          </button>
        )}
        {source && source.protocol !== 'local' && (
          <button
            type="button"
            className="settings-modal__option settings-modal__option--icon"
            onClick={handleReconnect}
            disabled={reconnecting}
            aria-label={t('settings.reconnect')}
            title={t('settings.reconnect')}
          >
            <RefreshCw size={14} />
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
                  className="settings-modal__option settings-modal__option--icon"
                  onClick={() => handleRestoreDetected(entry.id)}
                  disabled={restoringId === entry.id}
                  aria-label={t('settings.restoreDetected')}
                  title={t('settings.restoreDetected')}
                >
                  <RotateCcw size={14} />
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
