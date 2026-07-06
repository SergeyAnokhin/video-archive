import { useMemo, useState } from "react";
import { ArrowUpLeft, Folder, ImageIcon, Info, Play, RefreshCcw } from "lucide-react";

export default function FileBrowserPanel({
  treeItems,
  selectedDirectory,
  source,
  selectedFile,
  isWorking,
  files,
  searchQuery,
  onScanSource,
  onOpenPlayback,
  onRunDirectoryAction,
  onSelectDirectory,
  onSelectFile,
  onOpenFileDetails,
  renderIndicatorBadges,
  getFilePreviewImageUrl,
  formatDirectoryLabel,
  formatStatusLabel,
  t
}) {
  const [directoryAction, setDirectoryAction] = useState("preview");
  const normalizedSearch = searchQuery.trim().toLowerCase();
  const childDirectories = useMemo(
    () =>
      treeItems
        .filter((node) => node.path !== "" && node.parent_path === selectedDirectory)
        .filter((directory) => !normalizedSearch || directory.name.toLowerCase().includes(normalizedSearch)),
    [normalizedSearch, selectedDirectory, treeItems]
  );
  const visibleFiles = useMemo(
    () => files.filter((file) => !normalizedSearch || file.file_name.toLowerCase().includes(normalizedSearch)),
    [files, normalizedSearch]
  );
  const parentDirectory = selectedDirectory.includes("/") ? selectedDirectory.slice(0, selectedDirectory.lastIndexOf("/")) : "";
  const hasEntries = childDirectories.length || visibleFiles.length;
  const isFiltered = normalizedSearch.length > 0;

  function renderStateLamp(kind, state) {
    return (
      <span
        className={`state-lamp state-lamp-${state}`}
        title={kind === "convert" ? t("files.convertState", { state: formatStatusLabel(state) }) : t("files.previewState", { state: formatStatusLabel(state) })}
      />
    );
  }

  return (
    <section className="file-panel floating-library">
      <div className="panel browser-toolbar">
        <div className="panel-header compact-file-header">
        <div className="file-header-main">
          <p className="section-kicker">{t("files.kicker")}</p>
          <div className="file-header-title-row">
            <h2>{formatDirectoryLabel(selectedDirectory)}</h2>
            {selectedDirectory ? (
              <div className="inline-actions file-nav-actions">
              <button type="button" className="ghost-button nav-chip" onClick={() => onSelectDirectory(parentDirectory)}>
                <ArrowUpLeft size={15} />
              </button>
              <button type="button" className="ghost-button nav-chip" onClick={() => onSelectDirectory("")}>
                <Folder size={15} />
              </button>
              </div>
            ) : null}
          </div>
        </div>
        <div className="inline-actions toolbar-inline-cluster">
          <button
            type="button"
            className="ghost-button icon-only-button"
            disabled={!source || isWorking}
            aria-label={t("directory.rescanSource")}
            title={t("directory.rescanSource")}
            onClick={onScanSource}
          >
            <RefreshCcw size={16} />
          </button>
          <div className="directory-task-picker">
            <select value={directoryAction} onChange={(event) => setDirectoryAction(event.target.value)} disabled={!source || isWorking}>
              <option value="preview">{t("files.previewSubtree")}</option>
              <option value="convert">{t("files.convertSubtree")}</option>
              <option value="tag">{t("files.tagSubtree")}</option>
              <option value="rescan">{t("files.rescanSubtree")}</option>
            </select>
            <button
              type="button"
              className="primary-button icon-only-button"
              disabled={!source || isWorking}
              aria-label={t("files.runTask")}
              title={t("files.runTask")}
              onClick={() => onRunDirectoryAction(directoryAction)}
            >
              <Play size={15} />
            </button>
          </div>
        </div>
      </div>
      </div>

      <div className="file-list">
        {childDirectories.map((directory) => {
          const badges = renderIndicatorBadges(directory.indicators);
          return (
            <button
              key={directory.id}
              type="button"
              className="file-card directory-card"
              onClick={() => onSelectDirectory(directory.path)}
            >
              <div className="directory-card-main">
                <span className="directory-card-icon">
                  <Folder size={20} />
                </span>
                <div className="directory-card-copy">
                  <strong title={directory.name}>{directory.name}</strong>
                  <span>{t("files.folderCard")}</span>
                </div>
              </div>
              <div className="tree-badges directory-card-badges">
                {badges.map((badge) => (
                  <span key={badge.key} className={`tree-badge tree-badge-${badge.state}`} title={badge.title}>
                    {badge.label}
                  </span>
                ))}
              </div>
            </button>
          );
        })}

        {visibleFiles.map((file) => (
            <article
              key={file.id}
              className={`file-card ${selectedFile?.id === file.id ? "active" : ""}`}
              onClick={() => {
                onSelectFile(file.id);
                onOpenPlayback(file);
              }}
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
                      aria-label={t("files.details")}
                      title={t("files.details")}
                      onClick={(event) => {
                        event.stopPropagation();
                        onSelectFile(file.id);
                        onOpenFileDetails(file.id);
                      }}
                    >
                      <Info size={15} />
                    </button>
                  </div>
                </div>
              </div>

              <div className="file-card-body">
                <strong title={file.file_name}>{file.file_name}</strong>
              </div>
            </article>
          ))}
        {!hasEntries ? (
          <div className="empty-state">
            <h3>{isFiltered ? t("files.searchEmptyTitle") : t("files.emptyTitle")}</h3>
            <p>{isFiltered ? t("files.searchEmptyBody") : t("files.emptyBody")}</p>
          </div>
        ) : (
          null
        )}
      </div>
    </section>
  );
}
