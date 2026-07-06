import { ArrowUp, Folder, HardDriveDownload, Save, ScanSearch, ServerCog, TestTube2 } from "lucide-react";

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
  onSourceSave,
  t
}) {
  const favoriteLabelByKey = {
    repo_test_archive: t("sourceSettings.testArchive"),
    backend_folder: t("sourceSettings.backendFolder"),
    backend_local_data: t("sourceSettings.backendData")
  };

  return (
    <div className="source-settings">
      <p>{t("sourceSettings.intro")}</p>
      <div className="form-grid">
        <label>
          <span>{t("sourceSettings.name")}</span>
          <input value={sourceForm.name} onChange={(event) => onUpdateSourceField("name", event.target.value)} />
        </label>
        <label>
          <span>{t("sourceSettings.protocol")}</span>
          <select value={sourceForm.protocol} onChange={(event) => onUpdateSourceField("protocol", event.target.value)}>
            <option value="local">{t("sourceSettings.localOption")}</option>
            <option value="smb">SMB</option>
            <option value="ftp">FTP</option>
            <option value="sftp">SFTP</option>
            <option value="webdav">WebDAV</option>
          </select>
        </label>
        <label className="full-width">
          <span>{t("sourceSettings.rootPath")}</span>
          <input
            value={sourceForm.root_path}
            onChange={(event) => onUpdateSourceField("root_path", event.target.value)}
            placeholder={sourceFormIsLocal ? t("sourceSettings.localPlaceholder") : t("sourceSettings.remotePlaceholder")}
          />
        </label>
        {sourceFormIsLocal ? null : (
          <>
            <label>
              <span>{t("sourceSettings.host")}</span>
              <input value={sourceForm.host} onChange={(event) => onUpdateSourceField("host", event.target.value)} />
            </label>
            <label>
              <span>{t("sourceSettings.port")}</span>
              <input value={sourceForm.port} onChange={(event) => onUpdateSourceField("port", event.target.value)} placeholder={t("sourceSettings.portPlaceholder")} />
            </label>
            <label>
              <span>{t("sourceSettings.username")}</span>
              <input value={sourceForm.username} onChange={(event) => onUpdateSourceField("username", event.target.value)} />
            </label>
            <label>
              <span>{t("sourceSettings.password")}</span>
              <input
                type="password"
                value={sourceForm.password}
                onChange={(event) => onUpdateSourceField("password", event.target.value)}
                placeholder={source?.has_password ? t("sourceSettings.keepPassword") : ""}
              />
            </label>
          </>
        )}
      </div>
      {sourceFormIsLocal && localDirectoryBrowser.favorites?.length ? (
        <div className="note-card">
          <strong>{t("sourceSettings.favorites")}</strong>
          <div className="favorite-directory-list">
            {localDirectoryBrowser.favorites.map((entry) => (
              <button key={entry.id} type="button" className="mini-button icon-button" onClick={() => onSelectLocalDirectory(entry.path)}>
                <HardDriveDownload size={16} />
                <span>{favoriteLabelByKey[entry.label_key] ?? entry.path}</span>
              </button>
            ))}
          </div>
        </div>
      ) : null}
      <div className="inline-actions">
        {sourceFormIsLocal ? (
          <button
            type="button"
            className="ghost-button icon-button"
            disabled={isWorking}
            onClick={() => onLoadLocalDirectoryBrowser(localDirectoryBrowser.path || sourceForm.root_path || "")}
          >
            <Folder size={16} />
            <span>{t("sourceSettings.browse")}</span>
          </button>
        ) : null}
        <button type="button" className="ghost-button icon-button" disabled={isWorking} onClick={onSourceTest}>
          <TestTube2 size={16} />
          <span>{t("sourceSettings.test")}</span>
        </button>
        <button type="button" className="ghost-button icon-button" disabled={!source || isWorking} onClick={onReconnect}>
          <ServerCog size={16} />
          <span>{t("sourceSettings.reconnect")}</span>
        </button>
        <button type="button" className="ghost-button icon-button" disabled={!source || isWorking} onClick={onScanSource}>
          <ScanSearch size={16} />
          <span>{t("sourceSettings.scan")}</span>
        </button>
        <button type="button" className="primary-button icon-button" disabled={isWorking} onClick={onSourceSave}>
          <Save size={16} />
          <span>{t("sourceSettings.save")}</span>
        </button>
      </div>
      {sourceFormIsLocal && isLocalDirectoryBrowserOpen ? (
        <div className="note-card local-directory-browser">
          <div className="panel-header compact-header">
            <div>
              <strong>{t("sourceSettings.browseTitle")}</strong>
              <p className="muted">{localDirectoryBrowser.path || t("sourceSettings.browseRoot")}</p>
            </div>
            <div className="inline-actions">
              <button
                type="button"
                className="ghost-button icon-button"
                disabled={isWorking || !localDirectoryBrowser.parent_path}
                onClick={() => onLoadLocalDirectoryBrowser(localDirectoryBrowser.parent_path || "")}
              >
                <ArrowUp size={16} />
                <span>{t("sourceSettings.up")}</span>
              </button>
              <button
                type="button"
                className="primary-button icon-button"
                disabled={isWorking || !localDirectoryBrowser.path}
                onClick={() => onSelectLocalDirectory(localDirectoryBrowser.path)}
              >
                <Folder size={16} />
                <span>{t("sourceSettings.useFolder")}</span>
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
                <span>{t("sourceSettings.noChildren")}</span>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
      {testResult ? (
        <div className={`note-card ${testResult.ok ? "note-card-success" : "note-card-warning"}`}>
          <strong>{testResult.ok ? t("sourceSettings.ready") : t("sourceSettings.partial")}</strong>
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
