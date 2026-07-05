import { useEffect, useMemo, useState } from "react";
import { fallbackInfo, loadAppShellData } from "./api";
import {
  mockFilesByDirectory,
  mockJobs,
  mockLogs,
  mockTree,
  settingsSections
} from "./mockData";

function findDefaultDirectory(tree) {
  return tree[0]?.children?.[0]?.children?.[0]?.path ?? "/";
}

function flattenTree(nodes, depth = 0) {
  return nodes.flatMap((node) => [
    { ...node, depth },
    ...(node.children ? flattenTree(node.children, depth + 1) : [])
  ]);
}

function formatStatusLabel(value) {
  return value.replaceAll("_", " ");
}

function App() {
  const [health, setHealth] = useState({ state: "loading", status: null, error: null });
  const [info, setInfo] = useState(fallbackInfo);
  const [source, setSource] = useState(null);
  const [selectedDirectory, setSelectedDirectory] = useState(findDefaultDirectory(mockTree));
  const [selectedSettingsSection, setSelectedSettingsSection] = useState("source");
  const [previewVisible, setPreviewVisible] = useState(true);
  const [activeOverlay, setActiveOverlay] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const payload = await loadAppShellData();

        if (!cancelled) {
          setHealth({ state: "ready", status: payload.health.status, error: null });
          setInfo(payload.info);
          setSource(payload.source);
        }
      } catch (error) {
        if (!cancelled) {
          setHealth({ state: "error", status: null, error: error.message });
        }
      }
    }

    load();

    return () => {
      cancelled = true;
    };
  }, []);

  const treeItems = useMemo(() => flattenTree(mockTree), []);
  const files = mockFilesByDirectory[selectedDirectory] ?? [];
  const selectedFile = files[0] ?? null;
  const liveSourceLabel = source?.name ?? info.active_source?.name ?? "Shell preview";
  const liveSourceMeta = source
    ? `${source.protocol.toUpperCase()} - ${source.host}${source.root_path}`
    : "No active remote source configured";
  const queueSummary = `${info.queue.running_jobs} running - ${info.queue.queued_jobs} queued`;
  const backendLabel =
    health.state === "ready"
      ? `Backend ${health.status}`
      : health.state === "loading"
        ? "Connecting backend"
        : "Backend offline";

  return (
    <main className="app-shell">
      <header className="topbar panel">
        <div className="brand-block">
          <p className="eyebrow">Video Archive</p>
          <div className="brand-row">
            <h1>Library</h1>
            <span className={`status-pill status-pill-${health.state}`}>{backendLabel}</span>
          </div>
          <p className="summary">
            First frontend shell for browsing one source, checking queue health, and opening
            secondary surfaces without crowding the main library screen.
          </p>
          {health.error ? <p className="muted">Last backend error: {health.error}</p> : null}
        </div>

        <div className="toolbar">
          <div className="toolbar-card">
            <span className="toolbar-label">Source</span>
            <strong>{liveSourceLabel}</strong>
            <span className="toolbar-meta">{liveSourceMeta}</span>
          </div>

          <div className="toolbar-card compact">
            <span className="toolbar-label">Queue</span>
            <strong>{queueSummary}</strong>
            <span className="toolbar-meta">Runtime {info.queue.status}</span>
          </div>

          <div className="toolbar-actions">
            <button
              type="button"
              className="ghost-button"
              onClick={() => setPreviewVisible((value) => !value)}
            >
              {previewVisible ? "Hide preview" : "Show preview"}
            </button>
            <button type="button" className="ghost-button" onClick={() => setActiveOverlay("jobs")}>
              Jobs
            </button>
            <button type="button" className="ghost-button" onClick={() => setActiveOverlay("logs")}>
              Logs
            </button>
            <button
              type="button"
              className="primary-button"
              onClick={() => setActiveOverlay("settings")}
            >
              Settings
            </button>
          </div>
        </div>
      </header>

      <section className={`workspace ${previewVisible ? "with-preview" : "without-preview"}`}>
        <aside className="panel tree-panel">
          <div className="panel-header">
            <div>
              <p className="section-kicker">Directories</p>
              <h2>Tree</h2>
            </div>
            <button type="button" className="mini-button">
              Rescan
            </button>
          </div>

          <div className="tree-list">
            {treeItems.map((node) => (
              <button
                key={node.id}
                type="button"
                className={`tree-item ${selectedDirectory === node.path ? "active" : ""}`}
                style={{ paddingLeft: `${16 + node.depth * 16}px` }}
                onClick={() => setSelectedDirectory(node.path)}
              >
                <span>{node.name}</span>
                {node.path === "family/2024" ? <span className="tree-badge">preview</span> : null}
              </button>
            ))}
          </div>
        </aside>

        <section className="panel file-panel">
          <div className="panel-header">
            <div>
              <p className="section-kicker">Current folder</p>
              <h2>{selectedDirectory === "/" ? "Library root" : selectedDirectory}</h2>
            </div>
            <div className="inline-actions">
              <button type="button" className="mini-button">
                Convert
              </button>
              <button type="button" className="mini-button">
                Preview
              </button>
              <button type="button" className="mini-button">
                Tag
              </button>
            </div>
          </div>

          <div className="list-header">
            <span>Name</span>
            <span>Duration</span>
            <span>Size</span>
            <span>Modified</span>
            <span>Status</span>
          </div>

          <div className="file-list">
            {files.length ? (
              files.map((file) => (
                <article key={file.id} className="file-row">
                  <div>
                    <strong>{file.name}</strong>
                    <p className="row-subtitle">Video shell item</p>
                  </div>
                  <span>{file.duration}</span>
                  <span>{file.size}</span>
                  <span>{file.modifiedAt}</span>
                  <div className="state-stack">
                    <span className={`state-pill state-${file.conversionState}`}>
                      Convert {formatStatusLabel(file.conversionState)}
                    </span>
                    <span className={`state-pill state-${file.previewState}`}>
                      Preview {formatStatusLabel(file.previewState)}
                    </span>
                  </div>
                </article>
              ))
            ) : (
              <div className="empty-state">
                <h3>No files in this shell view</h3>
                <p>
                  The list surface is ready for real `/api/files` integration. Until then, this
                  folder shows an intentional empty state instead of advanced controls.
                </p>
              </div>
            )}
          </div>
        </section>

        {previewVisible ? (
          <aside className="panel preview-panel">
            <div className="panel-header">
              <div>
                <p className="section-kicker">Preview</p>
                <h2>Visibility shell</h2>
              </div>
              <button type="button" className="mini-button">
                Details
              </button>
            </div>

            <div className="preview-card">
              <div className="preview-canvas">
                <span>Preview area</span>
              </div>
              <div className="preview-meta">
                <strong>{selectedFile?.name ?? "No file selected"}</strong>
                <p>
                  This area stays optional and lightweight so the main library remains focused on
                  tree navigation and file browsing.
                </p>
              </div>
            </div>

            <dl className="meta-list">
              <div>
                <dt>Playback mode</dt>
                <dd>Settings-controlled</dd>
              </div>
              <div>
                <dt>Preview workflow</dt>
                <dd>Separate job type</dd>
              </div>
              <div>
                <dt>Future extension</dt>
                <dd>Details modal and tuning entry</dd>
              </div>
            </dl>
          </aside>
        ) : null}
      </section>

      {activeOverlay === "jobs" ? (
        <div className="overlay-backdrop" onClick={() => setActiveOverlay(null)}>
          <section className="overlay panel modal-shell" onClick={(event) => event.stopPropagation()}>
            <div className="panel-header">
              <div>
                <p className="section-kicker">Tasks and jobs</p>
                <h2>Queue shell</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => setActiveOverlay(null)}>
                Close
              </button>
            </div>
            <div className="jobs-grid">
              {mockJobs.map((job) => (
                <article key={job.id} className="job-card">
                  <div className="job-header">
                    <strong>{job.label}</strong>
                    <span className={`state-pill state-${job.status}`}>{job.status}</span>
                  </div>
                  <p>{job.target}</p>
                  <p className="muted">{job.detail}</p>
                </article>
              ))}
            </div>
          </section>
        </div>
      ) : null}

      {activeOverlay === "logs" ? (
        <div className="overlay-backdrop" onClick={() => setActiveOverlay(null)}>
          <section className="overlay panel modal-shell" onClick={(event) => event.stopPropagation()}>
            <div className="panel-header">
              <div>
                <p className="section-kicker">Log viewer</p>
                <h2>Activity shell</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => setActiveOverlay(null)}>
                Close
              </button>
            </div>
            <div className="log-toolbar">
              <span className="toolbar-meta">Streaming UI reserved for later SSE integration</span>
              <div className="inline-actions">
                <button type="button" className="mini-button">
                  All levels
                </button>
                <button type="button" className="mini-button">
                  Current folder
                </button>
              </div>
            </div>
            <pre className="log-console">{mockLogs.join("\n")}</pre>
          </section>
        </div>
      ) : null}

      {activeOverlay === "settings" ? (
        <div className="overlay-backdrop" onClick={() => setActiveOverlay(null)}>
          <section
            className="overlay panel modal-shell settings-shell"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="panel-header">
              <div>
                <p className="section-kicker">Settings</p>
                <h2>Navigation shell</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => setActiveOverlay(null)}>
                Close
              </button>
            </div>
            <div className="settings-layout">
              <nav className="settings-nav">
                {settingsSections.map((section) => (
                  <button
                    key={section.id}
                    type="button"
                    className={`settings-link ${
                      selectedSettingsSection === section.id ? "active" : ""
                    }`}
                    onClick={() => setSelectedSettingsSection(section.id)}
                  >
                    {section.label}
                  </button>
                ))}
              </nav>
              <section className="settings-detail">
                <h3>{settingsSections.find((section) => section.id === selectedSettingsSection)?.label}</h3>
                <p>
                  This shell reserves stable navigation for source, preview, playback, providers,
                  backup, and maintenance without surfacing those advanced controls on the main
                  library screen.
                </p>
                <div className="settings-placeholder">
                  <span>Future page content</span>
                </div>
              </section>
            </div>
          </section>
        </div>
      ) : null}
    </main>
  );
}

export default App;
