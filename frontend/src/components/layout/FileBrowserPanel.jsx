export default function FileBrowserPanel({
  selectedDirectory,
  source,
  selectedFile,
  isWorking,
  files,
  onOpenDetails,
  onOpenPlayback,
  onOpenConvertDirectory,
  onPreviewDirectory,
  onTagDirectory,
  onRescanDirectory,
  onSelectFile,
  formatDirectoryLabel,
  formatBytes,
  formatDate,
  formatStatusLabel
}) {
  return (
    <section className="panel file-panel">
      <div className="panel-header">
        <div>
          <p className="section-kicker">Current folder</p>
          <h2>{formatDirectoryLabel(selectedDirectory)}</h2>
          <p className="muted">Primary toolbar stays focused on subtree work and lightweight file entry points.</p>
        </div>
        <div className="inline-actions">
          <button type="button" className="mini-button" disabled={!source || !selectedFile || isWorking} onClick={onOpenDetails}>
            Details
          </button>
          <button type="button" className="mini-button" disabled={!source || !selectedFile || isWorking} onClick={onOpenPlayback}>
            Open playback
          </button>
          <button type="button" className="mini-button" disabled={!source || isWorking} onClick={onOpenConvertDirectory}>
            Convert subtree
          </button>
          <button type="button" className="mini-button" disabled={!source || isWorking} onClick={onPreviewDirectory}>
            Preview subtree
          </button>
          <button type="button" className="mini-button" disabled={!source || isWorking} onClick={onTagDirectory}>
            Tag subtree
          </button>
          <button type="button" className="mini-button" disabled={!source || isWorking} onClick={onRescanDirectory}>
            Rescan subtree
          </button>
        </div>
      </div>

      <div className="list-header">
        <span>Name</span>
        <span>Type</span>
        <span>Size</span>
        <span>Modified</span>
        <span>Status</span>
      </div>

      <div className="file-list">
        {files.length ? (
          files.map((file) => (
            <article
              key={file.id}
              className={`file-row ${selectedFile?.id === file.id ? "active" : ""}`}
              onClick={() => onSelectFile(file.id)}
              onDoubleClick={onOpenDetails}
            >
              <div>
                <strong>{file.file_name}</strong>
                <p className="row-subtitle">{file.relative_path}</p>
              </div>
              <span>{file.extension || "-"}</span>
              <span>{formatBytes(file.size_bytes)}</span>
              <span>{formatDate(file.modified_at)}</span>
              <div className="state-stack">
                <span className={`state-pill state-${file.conversion_state}`}>
                  Convert {formatStatusLabel(file.conversion_state)}
                </span>
                <span className={`state-pill state-${file.preview_state}`}>
                  Preview {formatStatusLabel(file.preview_state)}
                </span>
              </div>
            </article>
          ))
        ) : (
          <div className="empty-state">
            <h3>No files in this folder</h3>
            <p>This folder either has no files yet or has not been discovered by a completed scan.</p>
          </div>
        )}
      </div>
    </section>
  );
}
