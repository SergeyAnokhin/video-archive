import { Folder, FolderOpen, RefreshCcw } from "lucide-react";

export default function DirectoryTreePanel({
  treeItems,
  selectedDirectory,
  source,
  isWorking,
  onScanSource,
  onSelectDirectory,
  renderIndicatorBadges,
  t
}) {
  return (
    <aside className="panel tree-panel">
      <div className="panel-header">
        <div>
          <p className="section-kicker">{t("directory.kicker")}</p>
          <h2>{t("directory.title")}</h2>
        </div>
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
      </div>

      <div className="tree-list">
        {treeItems.length ? (
          treeItems.map((node) => {
            const badges = renderIndicatorBadges(node.indicators);
            return (
              <button
                key={node.id}
                type="button"
                className={`tree-item ${selectedDirectory === node.path ? "active" : ""}`}
                onClick={() => onSelectDirectory(node.path)}
              >
                <span className="tree-item-main">
                  <span className="tree-depth-rail" style={{ width: `${node.depth * 14}px` }} aria-hidden="true" />
                  {selectedDirectory === node.path ? <FolderOpen size={15} /> : <Folder size={15} />}
                  <span className="tree-name">{node.path ? node.name : t("app.sourceRoot")}</span>
                </span>
                <span className="tree-badges">
                  {badges.map((badge) => (
                    <span key={badge.key} className={`tree-badge tree-badge-${badge.state}`} title={badge.title}>
                      {badge.label}
                    </span>
                  ))}
                </span>
              </button>
            );
          })
        ) : (
          <div className="empty-state compact">
            <h3>{t("directory.emptyTitle")}</h3>
            <p>{t("directory.emptyBody")}</p>
          </div>
        )}
      </div>
    </aside>
  );
}
