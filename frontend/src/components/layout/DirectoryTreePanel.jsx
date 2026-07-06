import { RefreshCcw } from "lucide-react";

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
        <button type="button" className="mini-button icon-button" disabled={!source || isWorking} onClick={onScanSource}>
          <RefreshCcw size={16} />
          <span>{t("directory.rescanSource")}</span>
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
                style={{ paddingLeft: `${16 + node.depth * 16}px` }}
                onClick={() => onSelectDirectory(node.path)}
              >
                <span>{node.path ? node.name : t("app.sourceRoot")}</span>
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
