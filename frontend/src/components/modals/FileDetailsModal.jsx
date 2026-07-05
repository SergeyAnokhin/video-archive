export default function FileDetailsModal({
  isOpen,
  selectedFile,
  selectedFileDetails,
  selectedFilePreview,
  selectedFileTags,
  selectedFileLogs,
  isWorking,
  onClose,
  onOpenPlayback,
  onOpenConvertDialog,
  onPreviewFile,
  onTagFile,
  onOpenTune,
  onOpenLogViewer,
  formatBytes,
  formatConfidence,
  formatDate,
  formatStatusLabel
}) {
  if (!isOpen) {
    return null;
  }

  return (
    <div className="overlay-backdrop" onClick={onClose}>
      <section className="overlay panel modal-shell details-shell" onClick={(event) => event.stopPropagation()}>
        <div className="panel-header">
          <div>
            <p className="section-kicker">Video details</p>
            <h2>{selectedFile?.file_name ?? "Selected file"}</h2>
          </div>
          <div className="inline-actions">
            <button type="button" className="ghost-button" onClick={onClose}>
              Close
            </button>
          </div>
        </div>

        {selectedFileDetails ? (
          <div className="details-grid">
            <div className="details-main">
              <div className="preview-canvas details-preview">
                {selectedFilePreview?.image_data_url ? (
                  <img className="preview-image" src={selectedFilePreview.image_data_url} alt="Selected video preview" />
                ) : (
                  <span>No file preview stored yet.</span>
                )}
              </div>

              <div className="note-card">
                <strong>File actions</strong>
                <div className="inline-actions split-actions">
                  <button type="button" className="mini-button" disabled={isWorking} onClick={() => onOpenPlayback(selectedFile)}>
                    Playback
                  </button>
                  <button type="button" className="mini-button" disabled={isWorking} onClick={() => onOpenConvertDialog("file", selectedFile)}>
                    Convert file
                  </button>
                  <button type="button" className="mini-button" disabled={isWorking} onClick={() => onPreviewFile(selectedFile.id)}>
                    Preview file
                  </button>
                  <button type="button" className="mini-button" disabled={isWorking} onClick={() => onTagFile(selectedFile.id)}>
                    Tag file
                  </button>
                  <button type="button" className="mini-button" disabled={isWorking} onClick={onOpenTune}>
                    Tune file
                  </button>
                  <button
                    type="button"
                    className="mini-button"
                    onClick={() => onOpenLogViewer({ jobId: "", fileId: selectedFile.id, level: "" })}
                  >
                    Filter logs
                  </button>
                </div>
              </div>

              <div className="job-events-block">
                <h4>Recent file activity</h4>
                <pre className="log-console details-log-console">
                  {selectedFileLogs.length
                    ? selectedFileLogs
                        .map((event) => `${formatDate(event.created_at)}  ${event.level.toUpperCase()}  ${event.message}`)
                        .join("\n")
                    : "No file-specific events yet."}
                </pre>
              </div>
            </div>

            <div className="details-side">
              <dl className="meta-list">
                <div>
                  <dt>Relative path</dt>
                  <dd>{selectedFileDetails.relative_path}</dd>
                </div>
                <div>
                  <dt>Absolute path</dt>
                  <dd className="break-value">{selectedFileDetails.path}</dd>
                </div>
                <div>
                  <dt>Size</dt>
                  <dd>{formatBytes(selectedFileDetails.size_bytes)}</dd>
                </div>
                <div>
                  <dt>Modified</dt>
                  <dd>{formatDate(selectedFileDetails.modified_at)}</dd>
                </div>
                <div>
                  <dt>Discovered</dt>
                  <dd>{formatDate(selectedFileDetails.discovered_at)}</dd>
                </div>
                <div>
                  <dt>Convert state</dt>
                  <dd>{formatStatusLabel(selectedFileDetails.conversion_state)}</dd>
                </div>
                <div>
                  <dt>Preview state</dt>
                  <dd>{formatStatusLabel(selectedFileDetails.preview_state)}</dd>
                </div>
                <div>
                  <dt>Last converted</dt>
                  <dd>{formatDate(selectedFileDetails.last_converted_at)}</dd>
                </div>
                <div>
                  <dt>Preview generated</dt>
                  <dd>{formatDate(selectedFileDetails.preview_generated_at)}</dd>
                </div>
              </dl>

              <div className="note-card">
                <strong>Assigned tags</strong>
                {selectedFileTags?.tags?.length ? (
                  <>
                    <div className="tag-pill-list">
                      {selectedFileTags.tags.map((tag) => (
                        <span key={`${tag.tag_key}-${tag.assigned_at}`} className="tree-badge tree-badge-in_progress">
                          {tag.display_name} {formatConfidence(tag.confidence)}
                        </span>
                      ))}
                    </div>
                    <p className="muted">
                      {selectedFileTags.tagging_model_info?.provider ?? "-"} - {selectedFileTags.tagging_model_info?.model ?? "-"}
                    </p>
                  </>
                ) : (
                  <p>No tags stored yet.</p>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="empty-state compact">
            <h3>Loading file details</h3>
            <p>Fetching metadata, preview, tags, and recent file activity.</p>
          </div>
        )}
      </section>
    </div>
  );
}
