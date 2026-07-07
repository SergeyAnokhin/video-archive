import { FolderCog, FolderInput, FlaskConical, ImagePlus, Play, SlidersHorizontal, Tags, TextSearch, Trash2, X } from "lucide-react";

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
  onMoveFile,
  onDeleteFile,
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

  const previewFileName = selectedFilePreview?.image_path ? selectedFilePreview.image_path.split(/[/\\]/).pop() : "";
  const taggingState = selectedFileTags?.tagging_updated_at ? "done" : "not_started";
  const statusRows = selectedFileDetails
    ? [
        { key: "convert", label: t("details.convertState"), state: selectedFileDetails.conversion_state },
        { key: "preview", label: t("details.previewState"), state: selectedFileDetails.preview_state },
        { key: "tag", label: t("details.tagState"), state: taggingState }
      ]
    : [];
  const mediaInfo = selectedFileDetails?.media_info ?? null;
  const lastProfile = selectedFileDetails?.last_conversion_profile ?? null;
  const generatedKind = selectedFileDetails?.generated_kind ?? null;

  function renderStateLamp(state) {
    return <span className={`state-lamp state-lamp-${state}`} aria-hidden="true" />;
  }

  function formatCodecLabel(value) {
    if (!value) {
      return "-";
    }
    const normalized = String(value).toLowerCase();
    return (
      {
        h264: "H.264",
        avc: "H.264",
        h265: "H.265",
        hevc: "H.265 / HEVC",
        av1: "AV1",
        aac: "AAC",
        opus: "Opus"
      }[normalized] ?? String(value).toUpperCase()
    );
  }

  function formatResolution(info) {
    if (!info?.width || !info?.height) {
      return "-";
    }
    return `${info.width}x${info.height}`;
  }

  function formatAspectRatio(info) {
    if (!info) {
      return "-";
    }
    if (info.display_aspect_ratio) {
      const decimalRatio = info.width && info.height ? ` (${(info.width / info.height).toFixed(2)}:1)` : "";
      return `${info.display_aspect_ratio}${decimalRatio}`;
    }
    if (!info.width || !info.height) {
      return "-";
    }
    const divisor = greatestCommonDivisor(info.width, info.height);
    return `${info.width / divisor}:${info.height / divisor} (${(info.width / info.height).toFixed(2)}:1)`;
  }

  function formatBitrate(value) {
    if (!Number.isFinite(value) || value <= 0) {
      return "-";
    }
    if (value >= 1_000_000) {
      return `${(value / 1_000_000).toFixed(2)} Mbps`;
    }
    return `${Math.round(value / 1000)} kbps`;
  }

  function formatDuration(value) {
    if (!Number.isFinite(value) || value < 0) {
      return "-";
    }
    const totalSeconds = Math.round(value);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    if (hours > 0) {
      return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    }
    return `${minutes}:${String(seconds).padStart(2, "0")}`;
  }

  function formatFrameRate(value) {
    if (!Number.isFinite(value) || value <= 0) {
      return "-";
    }
    return `${value >= 10 ? value.toFixed(2) : value.toFixed(3)} fps`;
  }

  function formatQuality(profile) {
    if (!profile?.quality_value) {
      return "-";
    }
    return `${String(profile.quality_mode || "quality").toUpperCase()} ${profile.quality_value}`;
  }

  return (
    <div className="overlay-backdrop" onClick={onClose}>
      <section className="overlay panel modal-shell details-shell" onClick={(event) => event.stopPropagation()}>
        <div className="panel-header details-header">
          <div>
            <p className="section-kicker">{t("details.kicker")}</p>
            <h2>{selectedFile?.file_name ?? t("details.titleFallback")}</h2>
            {selectedFileDetails?.relative_path ? <p className="details-subtitle">{selectedFileDetails.relative_path}</p> : null}
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
              <button type="button" className="preview-canvas details-preview details-play-surface" onClick={() => onOpenPlayback(selectedFile)}>
                {selectedFilePreview?.image_data_url ? (
                  <img className="preview-image" src={selectedFilePreview.image_data_url} alt="Selected video preview" />
                ) : (
                  <span>{t("details.noPreview")}</span>
                )}
                <span className="details-play-overlay">
                  <Play size={18} />
                  <span>{t("details.openPlayback")}</span>
                </span>
              </button>

              <div className="note-card details-status-card">
                <strong>{t("details.statusLine")}</strong>
                <div className="details-status-row">
                  {statusRows.map((entry) => (
                    <span key={entry.key} className="details-status-item">
                      {renderStateLamp(entry.state)}
                      <span>
                        {entry.label}: {formatStatusLabel(entry.state)}
                      </span>
                    </span>
                  ))}
                </div>
              </div>

              <div className="note-card details-actions-card">
                <strong>{t("details.actions")}</strong>
                <div className="inline-actions split-actions details-actions-row">
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
                  <button type="button" className="mini-button icon-button" disabled={isWorking} onClick={() => onMoveFile(selectedFile)}>
                    <FolderInput size={16} />
                    <span>{t("details.move")}</span>
                  </button>
                  <button type="button" className="mini-button icon-button danger-button" disabled={isWorking} onClick={() => onDeleteFile(selectedFile)}>
                    <Trash2 size={16} />
                    <span>{t("details.delete")}</span>
                  </button>
                </div>
              </div>

              {generatedKind ? (
                <div className="note-card details-summary-card">
                  <strong>{t("details.generatedBlock")}</strong>
                  <div className="details-status-row">
                    <span className="details-status-item">
                      <FlaskConical size={16} />
                      <span>{generatedKind === "tune" ? t("details.generatedTune") : t("details.generatedTest")}</span>
                    </span>
                  </div>
                </div>
              ) : null}

              {selectedFilePreview?.image_path ? (
                <div className="note-card">
                  <strong>{t("details.previewAsset")}</strong>
                  <dl className="meta-list compact-meta-list">
                    <div>
                      <dt>{t("details.previewFileName")}</dt>
                      <dd className="break-value">{previewFileName}</dd>
                    </div>
                    <div>
                      <dt>{t("details.previewFilePath")}</dt>
                      <dd className="break-value">{selectedFilePreview.image_path}</dd>
                    </div>
                  </dl>
                </div>
              ) : null}
            </div>

            <div className="details-side">
              <div className="note-card details-summary-card">
                <strong>{t("details.summary")}</strong>
                <div className="details-fact-grid">
                  <div className="details-fact-tile">
                    <span className="details-fact-label">{t("details.size")}</span>
                    <strong>{formatBytes(selectedFileDetails.size_bytes)}</strong>
                  </div>
                  <div className="details-fact-tile">
                    <span className="details-fact-label">{t("details.resolution")}</span>
                    <strong>{formatResolution(mediaInfo)}</strong>
                  </div>
                  <div className="details-fact-tile">
                    <span className="details-fact-label">{t("details.aspectRatio")}</span>
                    <strong>{formatAspectRatio(mediaInfo)}</strong>
                  </div>
                  <div className="details-fact-tile">
                    <span className="details-fact-label">{t("details.duration")}</span>
                    <strong>{formatDuration(mediaInfo?.duration_seconds)}</strong>
                  </div>
                </div>
                <dl className="meta-list details-meta-list">
                  <div>
                    <dt>{t("details.modified")}</dt>
                    <dd>{formatDate(selectedFileDetails.modified_at)}</dd>
                  </div>
                  <div>
                    <dt>{t("details.discovered")}</dt>
                    <dd>{formatDate(selectedFileDetails.discovered_at)}</dd>
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
              </div>

              <div className="note-card details-summary-card">
                <strong>{t("details.codecBlock")}</strong>
                <dl className="meta-list details-meta-list">
                  <div>
                    <dt>{t("details.videoCodec")}</dt>
                    <dd>{formatCodecLabel(mediaInfo?.video_codec)}</dd>
                  </div>
                  <div>
                    <dt>{t("details.codecProfile")}</dt>
                    <dd>{mediaInfo?.video_profile || "-"}</dd>
                  </div>
                  <div>
                    <dt>{t("details.audioCodec")}</dt>
                    <dd>{formatCodecLabel(mediaInfo?.audio_codec)}</dd>
                  </div>
                  <div>
                    <dt>{t("details.bitrate")}</dt>
                    <dd>{formatBitrate(mediaInfo?.bitrate_bps)}</dd>
                  </div>
                  <div>
                    <dt>{t("details.frameRate")}</dt>
                    <dd>{formatFrameRate(mediaInfo?.frame_rate)}</dd>
                  </div>
                  <div>
                    <dt>{t("details.pixelFormat")}</dt>
                    <dd>{mediaInfo?.pixel_format || "-"}</dd>
                  </div>
                </dl>
              </div>

              <div className="note-card details-summary-card">
                <strong>{t("details.profileBlock")}</strong>
                {lastProfile ? (
                  <>
                    <div className="details-profile-name">{lastProfile.name}</div>
                    <dl className="meta-list details-meta-list">
                      <div>
                        <dt>{t("details.videoCodec")}</dt>
                        <dd>{formatCodecLabel(lastProfile.video_codec)}</dd>
                      </div>
                      <div>
                        <dt>{t("details.container")}</dt>
                        <dd>{String(lastProfile.container || "-").toUpperCase()}</dd>
                      </div>
                      <div>
                        <dt>{t("details.targetResolution")}</dt>
                        <dd>{lastProfile.max_dimension ? `${lastProfile.max_dimension}px` : t("details.sourceResolution")}</dd>
                      </div>
                      <div>
                        <dt>{t("details.quality")}</dt>
                        <dd>{formatQuality(lastProfile)}</dd>
                      </div>
                      <div>
                        <dt>{t("details.audioMode")}</dt>
                        <dd>{lastProfile.drop_audio ? t("details.audioDropped") : t("details.audioKept")}</dd>
                      </div>
                    </dl>
                  </>
                ) : (
                  <p className="muted">{t("details.noProfile")}</p>
                )}
              </div>

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

            <div className="job-events-block details-activity-block">
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

function greatestCommonDivisor(a, b) {
  let left = Math.abs(Number(a) || 0);
  let right = Math.abs(Number(b) || 0);
  while (right) {
    const next = left % right;
    left = right;
    right = next;
  }
  return left || 1;
}
