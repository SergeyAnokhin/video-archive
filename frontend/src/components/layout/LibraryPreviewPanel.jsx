import { Settings2 } from "lucide-react";

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
  formatDate,
  t
}) {
  return (
    <aside className="panel preview-panel">
      <div className="panel-header">
        <div>
          <p className="section-kicker">{t("previewPanel.kicker")}</p>
          <h2>{libraryPreview?.scope === "directory" ? t("previewPanel.directoryTitle") : t("previewPanel.fileTitle")}</h2>
        </div>
        <button type="button" className="mini-button icon-button" onClick={onOpenPreviewSettings}>
          <Settings2 size={16} />
          <span>{t("previewPanel.settings")}</span>
        </button>
      </div>

      <div className="preview-card">
        <div className="preview-canvas">
          {libraryPreview?.image_data_url ? (
            <img className="preview-image" src={libraryPreview.image_data_url} alt="Generated preview collage" />
          ) : (
            <span>{t("previewPanel.empty")}</span>
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
              ? t("previewPanel.summary", {
                  sampleCount: libraryPreview.metadata.sample_count,
                  largeTileCount: libraryPreview.metadata.large_tile_count,
                  timelineFlow: libraryPreview.metadata.timeline_flow
                })
              : t("previewPanel.fallbackSummary")}
          </p>
        </div>
      </div>

      <dl className="meta-list">
        <div>
          <dt>{t("previewPanel.selectedFolder")}</dt>
          <dd>{formatDirectoryLabel(selectedDirectory)}</dd>
        </div>
        <div>
          <dt>{t("previewPanel.visibleFiles")}</dt>
          <dd>{files.length}</dd>
        </div>
        <div>
          <dt>{t("previewPanel.selectedFile")}</dt>
          <dd>{selectedFile?.file_name ?? "-"}</dd>
        </div>
        <div>
          <dt>{t("previewPanel.assignedTags")}</dt>
          <dd>{selectedFileTags?.tags?.length ?? 0}</dd>
        </div>
        <div>
          <dt>{t("previewPanel.sampleCount")}</dt>
          <dd>{libraryPreview?.metadata?.sample_count ?? "-"}</dd>
        </div>
        <div>
          <dt>{t("previewPanel.playbackMode")}</dt>
          <dd>{playbackSettings.mode}</dd>
        </div>
        <div>
          <dt>{t("previewPanel.aspectRatio")}</dt>
          <dd>{libraryPreview?.metadata?.aspect_ratio_preset ?? "-"}</dd>
        </div>
      </dl>

      <div className="note-card">
        <strong>{t("previewPanel.closedVocabulary")}</strong>
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
          <p>{t("previewPanel.noTags")}</p>
        )}
      </div>
    </aside>
  );
}
