export default function AppHeader({
  health,
  backendLabel,
  actionError,
  actionMessage,
  liveSourceLabel,
  liveSourceMeta,
  queueSummary,
  queueStatus,
  previewVisible,
  source,
  isWorking,
  onTogglePreview,
  onScanSource,
  onOpenLogs,
  onOpenJobs,
  onOpenSettings
}) {
  return (
    <header className="topbar panel">
      <div className="brand-block">
        <p className="eyebrow">Video Archive</p>
        <div className="brand-row">
          <h1>Library</h1>
          <span className={`status-pill status-pill-${health.state}`}>{backendLabel}</span>
        </div>
        <p className="summary">
          Browse one active source, keep the main library light, and move playback, tuning, logs,
          and deeper file actions into dedicated modal flows.
        </p>
        {health.error ? <p className="muted">Last backend error: {health.error}</p> : null}
        {actionError ? <p className="feedback error">{actionError}</p> : null}
        {actionMessage ? <p className="feedback">{actionMessage}</p> : null}
      </div>

      <div className="toolbar">
        <div className="toolbar-card">
          <span className="toolbar-label">Source</span>
          <strong>{liveSourceLabel}</strong>
          <span className="toolbar-meta">{liveSourceMeta}</span>
        </div>

        <div className="toolbar-card compact">
          <span className="toolbar-label">Queue</span>
          <strong>{queueSummary}</strong>
          <span className="toolbar-meta">Runtime {queueStatus}</span>
        </div>

        <div className="toolbar-actions">
          <button type="button" className="ghost-button" onClick={onTogglePreview}>
            {previewVisible ? "Hide preview" : "Show preview"}
          </button>
          <button type="button" className="ghost-button" disabled={!source || isWorking} onClick={onScanSource}>
            Scan source
          </button>
          <button type="button" className="ghost-button" onClick={onOpenLogs}>
            Logs
          </button>
          <button type="button" className="ghost-button" onClick={onOpenJobs}>
            Jobs
          </button>
          <button type="button" className="primary-button" onClick={onOpenSettings}>
            Settings
          </button>
        </div>
      </div>
    </header>
  );
}
