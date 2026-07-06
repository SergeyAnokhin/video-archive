import { Clapperboard, Eye, FolderCog, ImagePlus, ScanSearch, Tags } from "lucide-react";

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
  formatStatusLabel,
  t
}) {
  return (
    <section className="panel file-panel">
      <div className="panel-header">
        <div>
          <p className="section-kicker">{t("files.kicker")}</p>
          <h2>{formatDirectoryLabel(selectedDirectory)}</h2>
          <p className="muted">{t("files.intro")}</p>
        </div>
        <div className="inline-actions">
          <button type="button" className="mini-button icon-button" disabled={!source || !selectedFile || isWorking} onClick={onOpenDetails}>
            <FolderCog size={16} />
            <span>{t("files.details")}</span>
          </button>
          <button type="button" className="mini-button icon-button" disabled={!source || !selectedFile || isWorking} onClick={onOpenPlayback}>
            <Clapperboard size={16} />
            <span>{t("files.playback")}</span>
          </button>
          <button type="button" className="mini-button icon-button" disabled={!source || isWorking} onClick={onOpenConvertDirectory}>
            <FolderCog size={16} />
            <span>{t("files.convertSubtree")}</span>
          </button>
          <button type="button" className="mini-button icon-button" disabled={!source || isWorking} onClick={onPreviewDirectory}>
            <ImagePlus size={16} />
            <span>{t("files.previewSubtree")}</span>
          </button>
          <button type="button" className="mini-button icon-button" disabled={!source || isWorking} onClick={onTagDirectory}>
            <Tags size={16} />
            <span>{t("files.tagSubtree")}</span>
          </button>
          <button type="button" className="mini-button icon-button" disabled={!source || isWorking} onClick={onRescanDirectory}>
            <ScanSearch size={16} />
            <span>{t("files.rescanSubtree")}</span>
          </button>
        </div>
      </div>

      <div className="list-header">
        <span>{t("files.name")}</span>
        <span>{t("files.type")}</span>
        <span>{t("files.size")}</span>
        <span>{t("files.modified")}</span>
        <span>{t("files.status")}</span>
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
                  {t("files.convertState", { state: formatStatusLabel(file.conversion_state) })}
                </span>
                <span className={`state-pill state-${file.preview_state}`}>
                  {t("files.previewState", { state: formatStatusLabel(file.preview_state) })}
                </span>
              </div>
            </article>
          ))
        ) : (
          <div className="empty-state">
            <h3>{t("files.emptyTitle")}</h3>
            <p>{t("files.emptyBody")}</p>
          </div>
        )}
      </div>
    </section>
  );
}
