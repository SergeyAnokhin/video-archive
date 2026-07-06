import { Clapperboard, FolderCog, ImagePlus, SlidersHorizontal, Tags, TextSearch, X } from "lucide-react";

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
  formatStatusLabel,
  t
}) {
  if (!isOpen) {
    return null;
  }

  return (
    <div className="overlay-backdrop" onClick={onClose}>
      <section className="overlay panel modal-shell details-shell" onClick={(event) => event.stopPropagation()}>
        <div className="panel-header">
          <div>
            <p className="section-kicker">{t("details.kicker")}</p>
            <h2>{selectedFile?.file_name ?? t("details.titleFallback")}</h2>
          </div>
          <div className="inline-actions">
            <button type="button" className="ghost-button icon-only-button" aria-label={t("common.close")} title={t("common.close")} onClick={onClose}>
              <X size={16} />
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
                  <span>{t("details.noPreview")}</span>
                )}
              </div>

              <div className="note-card">
                <strong>{t("details.actions")}</strong>
                <div className="inline-actions split-actions">
                  <button type="button" className="mini-button icon-button" disabled={isWorking} onClick={() => onOpenPlayback(selectedFile)}>
                    <Clapperboard size={16} />
                    <span>{t("details.playback")}</span>
                  </button>
                  <button type="button" className="mini-button icon-button" disabled={isWorking} onClick={() => onOpenConvertDialog("file", selectedFile)}>
                    <FolderCog size={16} />
                    <span>{t("details.convert")}</span>
                  </button>
                  <button type="button" className="mini-button icon-button" disabled={isWorking} onClick={() => onPreviewFile(selectedFile.id)}>
                    <ImagePlus size={16} />
                    <span>{t("details.preview")}</span>
                  </button>
                  <button type="button" className="mini-button icon-button" disabled={isWorking} onClick={() => onTagFile(selectedFile.id)}>
                    <Tags size={16} />
                    <span>{t("details.tag")}</span>
                  </button>
                  <button type="button" className="mini-button icon-button" disabled={isWorking} onClick={onOpenTune}>
                    <SlidersHorizontal size={16} />
                    <span>{t("details.tune")}</span>
                  </button>
                  <button
                    type="button"
                    className="mini-button icon-button"
                    onClick={() => onOpenLogViewer({ jobId: "", fileId: selectedFile.id, level: "" })}
                  >
                    <TextSearch size={16} />
                    <span>{t("details.logs")}</span>
                  </button>
                </div>
              </div>

              <div className="job-events-block">
                <h4>{t("details.activity")}</h4>
                <pre className="log-console details-log-console">
                  {selectedFileLogs.length
                    ? selectedFileLogs
                        .map((event) => `${formatDate(event.created_at)}  ${event.level.toUpperCase()}  ${event.message}`)
                        .join("\n")
                    : t("details.noEvents")}
                </pre>
              </div>
            </div>

            <div className="details-side">
              <dl className="meta-list">
                <div>
                  <dt>{t("details.relativePath")}</dt>
                  <dd>{selectedFileDetails.relative_path}</dd>
                </div>
                <div>
                  <dt>{t("details.absolutePath")}</dt>
                  <dd className="break-value">{selectedFileDetails.path}</dd>
                </div>
                <div>
                  <dt>{t("details.size")}</dt>
                  <dd>{formatBytes(selectedFileDetails.size_bytes)}</dd>
                </div>
                <div>
                  <dt>{t("details.modified")}</dt>
                  <dd>{formatDate(selectedFileDetails.modified_at)}</dd>
                </div>
                <div>
                  <dt>{t("details.discovered")}</dt>
                  <dd>{formatDate(selectedFileDetails.discovered_at)}</dd>
                </div>
                <div>
                  <dt>{t("details.convertState")}</dt>
                  <dd>{formatStatusLabel(selectedFileDetails.conversion_state)}</dd>
                </div>
                <div>
                  <dt>{t("details.previewState")}</dt>
                  <dd>{formatStatusLabel(selectedFileDetails.preview_state)}</dd>
                </div>
                <div>
                  <dt>{t("details.lastConverted")}</dt>
                  <dd>{formatDate(selectedFileDetails.last_converted_at)}</dd>
                </div>
                <div>
                  <dt>{t("details.previewGenerated")}</dt>
                  <dd>{formatDate(selectedFileDetails.preview_generated_at)}</dd>
                </div>
              </dl>

              <div className="note-card">
                <strong>{t("details.assignedTags")}</strong>
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
                  <p>{t("details.noTags")}</p>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="empty-state compact">
            <h3>{t("details.loadingTitle")}</h3>
            <p>{t("details.loadingBody")}</p>
          </div>
        )}
      </section>
    </div>
  );
}
