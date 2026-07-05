export default function LibraryPreviewPanel({
  libraryPreview,
  selectedDirectory,
  files,
  selectedFile,
  selectedFileTags,
  playbackSettings,
  onOpenPreviewSettings,
  formatDirectoryLabel,
  formatConfidence,
  formatDate
}) {
  return (
    <aside className="panel preview-panel">
      <div className="panel-header">
        <div>
          <p className="section-kicker">Preview</p>
          <h2>{libraryPreview?.scope === "directory" ? "Directory collage" : "Selected asset"}</h2>
        </div>
        <button type="button" className="mini-button" onClick={onOpenPreviewSettings}>
          Preview settings
        </button>
      </div>

      <div className="preview-card">
        <div className="preview-canvas">
          {libraryPreview?.image_data_url ? (
            <img className="preview-image" src={libraryPreview.image_data_url} alt="Generated preview collage" />
          ) : (
            <span>No preview asset yet. Run a file or subtree preview job.</span>
          )}
        </div>
        <div className="preview-meta">
          <strong>
            {libraryPreview?.scope === "directory"
              ? formatDirectoryLabel(selectedDirectory)
              : selectedFile?.file_name ?? "No file selected"}
          </strong>
          <p>
            {libraryPreview?.metadata
              ? `${libraryPreview.metadata.sample_count} sampled frames with ${libraryPreview.metadata.large_tile_count} large tiles in ${libraryPreview.metadata.timeline_flow} flow.`
              : "Preview generation is on-demand and remains separate from conversion and tagging."}
          </p>
        </div>
      </div>

      <dl className="meta-list">
        <div>
          <dt>Selected folder</dt>
          <dd>{formatDirectoryLabel(selectedDirectory)}</dd>
        </div>
        <div>
          <dt>Visible files</dt>
          <dd>{files.length}</dd>
        </div>
        <div>
          <dt>Selected file</dt>
          <dd>{selectedFile?.file_name ?? "-"}</dd>
        </div>
        <div>
          <dt>Assigned tags</dt>
          <dd>{selectedFileTags?.tags?.length ?? 0}</dd>
        </div>
        <div>
          <dt>Sample count</dt>
          <dd>{libraryPreview?.metadata?.sample_count ?? "-"}</dd>
        </div>
        <div>
          <dt>Playback mode</dt>
          <dd>{playbackSettings.mode}</dd>
        </div>
      </dl>

      <div className="note-card">
        <strong>Closed-vocabulary tags</strong>
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
              {selectedFileTags.tagging_model_info?.provider ?? "-"} - {selectedFileTags.tagging_model_info?.model ?? "-"} -{" "}
              {selectedFileTags.tagging_updated_at ? formatDate(selectedFileTags.tagging_updated_at) : "-"}
            </p>
          </>
        ) : (
          <p>No tags stored for the selected video yet. Run a file or subtree tagging job.</p>
        )}
      </div>
    </aside>
  );
}
