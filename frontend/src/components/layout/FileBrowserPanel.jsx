import { Clapperboard, FolderCog, ImageIcon, ImagePlus, ScanSearch, Tags } from "lucide-react";

export default function FileBrowserPanel({
  selectedDirectory,
  source,
  selectedFile,
  isWorking,
  files,
  onOpenPlayback,
  onOpenConvertDirectory,
  onPreviewDirectory,
  onTagDirectory,
  onRescanDirectory,
  onSelectFile,
  onOpenFileDetails,
  getFilePreviewImageUrl,
  formatDirectoryLabel,
  formatStatusLabel,
  t
}) {
  function renderStateLamp(kind, state) {
    return (
      <span
        className={`state-lamp state-lamp-${state}`}
        title={kind === "convert" ? t("files.convertState", { state: formatStatusLabel(state) }) : t("files.previewState", { state: formatStatusLabel(state) })}
      />
    );
  }

  return (
    <section className="panel file-panel">
      <div className="panel-header compact-file-header">
        <div>
          <p className="section-kicker">{t("files.kicker")}</p>
          <h2>{formatDirectoryLabel(selectedDirectory)}</h2>
        </div>
        <div className="inline-actions">
          <button
            type="button"
            className="ghost-button icon-only-button"
            disabled={!source || isWorking}
            aria-label={t("files.convertSubtree")}
            title={t("files.convertSubtree")}
            onClick={onOpenConvertDirectory}
          >
            <FolderCog size={16} />
          </button>
          <button
            type="button"
            className="ghost-button icon-only-button"
            disabled={!source || isWorking}
            aria-label={t("files.previewSubtree")}
            title={t("files.previewSubtree")}
            onClick={onPreviewDirectory}
          >
            <ImagePlus size={16} />
          </button>
          <button
            type="button"
            className="ghost-button icon-only-button"
            disabled={!source || isWorking}
            aria-label={t("files.tagSubtree")}
            title={t("files.tagSubtree")}
            onClick={onTagDirectory}
          >
            <Tags size={16} />
          </button>
          <button
            type="button"
            className="ghost-button icon-only-button"
            disabled={!source || isWorking}
            aria-label={t("files.rescanSubtree")}
            title={t("files.rescanSubtree")}
            onClick={onRescanDirectory}
          >
            <ScanSearch size={16} />
          </button>
        </div>
      </div>

      <div className="file-list">
        {files.length ? (
          files.map((file) => (
            <article
              key={file.id}
              className={`file-card ${selectedFile?.id === file.id ? "active" : ""}`}
              onClick={() => onSelectFile(file.id)}
              onDoubleClick={() => onOpenPlayback(file)}
            >
              <div className="file-card-media">
                {getFilePreviewImageUrl(file) ? (
                  <img className="preview-image" src={getFilePreviewImageUrl(file)} alt={file.file_name} loading="lazy" />
                ) : (
                  <div className="file-card-placeholder">
                    <ImageIcon size={20} />
                  </div>
                )}
                <div className="file-card-chrome">
                  <div className="file-card-indicators">
                    {renderStateLamp("convert", file.conversion_state)}
                    {renderStateLamp("preview", file.preview_state)}
                  </div>
                  <div className="file-card-actions">
                    <button
                      type="button"
                      className="ghost-button icon-only-button file-card-action"
                      disabled={isWorking}
                      aria-label={t("files.playback")}
                      title={t("files.playback")}
                      onClick={(event) => {
                        event.stopPropagation();
                        onOpenPlayback(file);
                      }}
                    >
                      <Clapperboard size={15} />
                    </button>
                    <button
                      type="button"
                      className="ghost-button icon-only-button file-card-action"
                      disabled={isWorking}
                      aria-label={t("files.details")}
                      title={t("files.details")}
                      onClick={(event) => {
                        event.stopPropagation();
                        onOpenFileDetails(file.id);
                      }}
                    >
                      <FolderCog size={15} />
                    </button>
                  </div>
                </div>
              </div>

              <div className="file-card-body">
                <strong title={file.file_name}>{file.file_name}</strong>
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
