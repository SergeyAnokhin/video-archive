export default function SourceSettingsSection({
  source,
  sourceForm,
  sourceFormIsLocal,
  isWorking,
  localDirectoryBrowser,
  isLocalDirectoryBrowserOpen,
  testResult,
  onUpdateSourceField,
  onLoadLocalDirectoryBrowser,
  onSelectLocalDirectory,
  onSourceTest,
  onReconnect,
  onScanSource,
  onSourceSave
}) {
  return (
    <div className="source-settings">
      <p>
        Video Archive supports one active source at a time. Use a remote protocol for server-backed libraries or switch to a local folder when you want to test directly on this machine.
      </p>
      <div className="form-grid">
        <label>
          <span>Name</span>
          <input value={sourceForm.name} onChange={(event) => onUpdateSourceField("name", event.target.value)} />
        </label>
        <label>
          <span>Protocol</span>
          <select value={sourceForm.protocol} onChange={(event) => onUpdateSourceField("protocol", event.target.value)}>
            <option value="local">Local folder</option>
            <option value="smb">SMB</option>
            <option value="ftp">FTP</option>
            <option value="sftp">SFTP</option>
            <option value="webdav">WebDAV</option>
          </select>
        </label>
        <label className="full-width">
          <span>Root path</span>
          <input
            value={sourceForm.root_path}
            onChange={(event) => onUpdateSourceField("root_path", event.target.value)}
            placeholder={sourceFormIsLocal ? "C:\\Videos\\Test Library" : "Accessible path or UNC share"}
          />
        </label>
        {sourceFormIsLocal ? null : (
          <>
            <label>
              <span>Host</span>
              <input value={sourceForm.host} onChange={(event) => onUpdateSourceField("host", event.target.value)} />
            </label>
            <label>
              <span>Port</span>
              <input value={sourceForm.port} onChange={(event) => onUpdateSourceField("port", event.target.value)} placeholder="Default" />
            </label>
            <label>
              <span>Username</span>
              <input value={sourceForm.username} onChange={(event) => onUpdateSourceField("username", event.target.value)} />
            </label>
            <label>
              <span>Password</span>
              <input
                type="password"
                value={sourceForm.password}
                onChange={(event) => onUpdateSourceField("password", event.target.value)}
                placeholder={source?.has_password ? "Leave blank to keep saved password" : ""}
              />
            </label>
          </>
        )}
      </div>
      <div className="inline-actions">
        {sourceFormIsLocal ? (
          <button
            type="button"
            className="ghost-button"
            disabled={isWorking}
            onClick={() => onLoadLocalDirectoryBrowser(localDirectoryBrowser.path || sourceForm.root_path || "")}
          >
            Browse local folders
          </button>
        ) : null}
        <button type="button" className="ghost-button" disabled={isWorking} onClick={onSourceTest}>
          Test connection
        </button>
        <button type="button" className="ghost-button" disabled={!source || isWorking} onClick={onReconnect}>
          Reconnect
        </button>
        <button type="button" className="ghost-button" disabled={!source || isWorking} onClick={onScanSource}>
          Scan source
        </button>
        <button type="button" className="primary-button" disabled={isWorking} onClick={onSourceSave}>
          Save source
        </button>
      </div>
      {sourceFormIsLocal && isLocalDirectoryBrowserOpen ? (
        <div className="note-card local-directory-browser">
          <div className="panel-header compact-header">
            <div>
              <strong>Local folder browser</strong>
              <p className="muted">{localDirectoryBrowser.path || "This PC"}</p>
            </div>
            <div className="inline-actions">
              <button
                type="button"
                className="ghost-button"
                disabled={isWorking || !localDirectoryBrowser.parent_path}
                onClick={() => onLoadLocalDirectoryBrowser(localDirectoryBrowser.parent_path || "")}
              >
                Up
              </button>
              <button
                type="button"
                className="primary-button"
                disabled={isWorking || !localDirectoryBrowser.path}
                onClick={() => onSelectLocalDirectory(localDirectoryBrowser.path)}
              >
                Use this folder
              </button>
            </div>
          </div>
          <div className="local-directory-list">
            {localDirectoryBrowser.directories.map((entry) => (
              <button
                key={entry.path}
                type="button"
                className="tree-item local-directory-item"
                onClick={() => onLoadLocalDirectoryBrowser(entry.path)}
              >
                <span>{entry.name}</span>
                <span className="row-subtitle">{entry.path}</span>
              </button>
            ))}
            {!localDirectoryBrowser.directories.length ? (
              <div className="settings-placeholder compact-placeholder">
                <span>No child directories found here.</span>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
      {testResult ? (
        <div className={`note-card ${testResult.ok ? "note-card-success" : "note-card-warning"}`}>
          <strong>{testResult.ok ? "Ready to scan" : "Connection partial"}</strong>
          <p>{testResult.message}</p>
          <p className="muted">
            {testResult.protocol === "local"
              ? testResult.root_path
              : `${testResult.host}:${testResult.port} - ${testResult.root_path}`}
          </p>
        </div>
      ) : null}
    </div>
  );
}
