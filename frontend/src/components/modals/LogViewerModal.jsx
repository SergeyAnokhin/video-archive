export default function LogViewerModal({
  isOpen,
  onClose,
  logFilters,
  onChangeLogFilter,
  onClearFilters,
  logEvents,
  logConsoleRef,
  formatDate
}) {
  if (!isOpen) {
    return null;
  }

  return (
    <div className="overlay-backdrop" onClick={onClose}>
      <section className="overlay panel modal-shell logs-shell" onClick={(event) => event.stopPropagation()}>
        <div className="panel-header">
          <div>
            <p className="section-kicker">Log viewer</p>
            <h2>Near-real-time backend activity</h2>
          </div>
          <button type="button" className="ghost-button" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="log-filter-grid">
          <label>
            <span>Job id</span>
            <input value={logFilters.jobId} onChange={(event) => onChangeLogFilter("jobId", event.target.value)} />
          </label>
          <label>
            <span>File id</span>
            <input value={logFilters.fileId} onChange={(event) => onChangeLogFilter("fileId", event.target.value)} />
          </label>
          <label>
            <span>Level</span>
            <select value={logFilters.level} onChange={(event) => onChangeLogFilter("level", event.target.value)}>
              <option value="">All levels</option>
              <option value="debug">Debug</option>
              <option value="info">Info</option>
              <option value="warning">Warning</option>
              <option value="error">Error</option>
            </select>
          </label>
          <div className="inline-actions align-end">
            <button type="button" className="ghost-button" onClick={onClearFilters}>
              Clear filters
            </button>
          </div>
        </div>
        <pre ref={logConsoleRef} className="log-console tall-console">
          {logEvents.length
            ? logEvents.map((event) => `${formatDate(event.created_at)}  ${event.level.toUpperCase()}  ${event.message}`).join("\n")
            : "No events match the current filters."}
        </pre>
      </section>
    </div>
  );
}
