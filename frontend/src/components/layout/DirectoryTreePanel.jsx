export default function DirectoryTreePanel({
  treeItems,
  selectedDirectory,
  source,
  isWorking,
  onScanSource,
  onSelectDirectory,
  renderIndicatorBadges
}) {
  return (
    <aside className="panel tree-panel">
      <div className="panel-header">
        <div>
          <p className="section-kicker">Directories</p>
          <h2>Tree</h2>
        </div>
        <button type="button" className="mini-button" disabled={!source || isWorking} onClick={onScanSource}>
          Rescan source
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
                <span>{node.path ? node.name : "Source root"}</span>
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
            <h3>No scanned tree yet</h3>
            <p>Save an active source, then run a source scan to populate the directory tree.</p>
          </div>
        )}
      </div>
    </aside>
  );
}
