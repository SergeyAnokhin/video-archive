import { useEffect, useMemo, useState } from "react";
import {
  cancelJob,
  createConvertDirectoryJob,
  createConvertFileJob,
  createPreviewDirectoryJob,
  createPreviewFileJob,
  createRescanDirectoryJob,
  createScanSourceJob,
  createTagDirectoryJob,
  createPreviewLayout,
  fallbackInfo,
  fetchDirectoryPreview,
  fetchFilePreview,
  fetchJob,
  fetchJobItems,
  fetchFiles,
  fetchJobs,
  fetchLogs,
  fetchPreviewLayouts,
  fetchSettings,
  fetchTree,
  fetchConversionProfiles,
  generateLivePreview,
  loadAppShellData,
  reconnectSource,
  restartJob,
  saveSettings,
  saveSource,
  testSourceConnection,
  updatePreviewLayout
} from "./api";
import { settingsSections } from "./mockData";

const emptySourceForm = {
  name: "",
  protocol: "smb",
  host: "",
  port: "",
  root_path: "",
  username: "",
  password: ""
};

const defaultPreviewSettings = {
  sample_count: 9,
  large_tile_count: 2,
  timeline_flow: "row",
  identity_diversity_enabled: true,
  layout_preset_id: "default-preview-grid"
};

function flattenTree(nodes, depth = 0) {
  return nodes.flatMap((node) => [
    { ...node, depth },
    ...(node.children ? flattenTree(node.children, depth + 1) : [])
  ]);
}

function toSourceForm(source) {
  if (!source) {
    return emptySourceForm;
  }

  return {
    name: source.name ?? "",
    protocol: source.protocol ?? "smb",
    host: source.host ?? "",
    port: source.port ?? "",
    root_path: source.root_path ?? "",
    username: source.username ?? "",
    password: ""
  };
}

function toSourcePayload(form) {
  return {
    name: form.name.trim(),
    protocol: form.protocol,
    host: form.host.trim(),
    port: form.port === "" ? null : Number(form.port),
    root_path: form.root_path.trim(),
    username: form.username.trim() || null,
    password: form.password.trim() || null
  };
}

function formatStatusLabel(value) {
  return value.replaceAll("_", " ");
}

function formatBytes(value) {
  if (!Number.isFinite(value)) {
    return "-";
  }

  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size >= 10 || unitIndex === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[unitIndex]}`;
}

function formatDate(value) {
  if (!value) {
    return "-";
  }

  return new Date(value).toLocaleString();
}

function formatDirectoryLabel(path) {
  return path ? path : "Library root";
}

function formatProfileLabel(profile) {
  const parts = [`${profile.video_codec.toUpperCase()} -> ${profile.container.toUpperCase()}`];
  if (profile.max_dimension) {
    parts.push(`max ${profile.max_dimension}px`);
  }
  parts.push(profile.drop_audio ? "no audio" : "audio kept");
  return `${profile.name} (${parts.join(", ")})`;
}

function formatJobScope(job) {
  if (!job) {
    return "-";
  }

  if (job.scope_type === "source") {
    return "Active source";
  }

  if (job.scope_type === "directory") {
    return job.scope_ref || "Library root";
  }

  return job.scope_ref || "-";
}

function formatJobTypeLabel(value) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function renderIndicatorBadges(indicators) {
  return [
    indicators?.conversion
      ? { key: "conversion", label: "convert", state: indicators.conversion.state, title: indicators.conversion.message }
      : null,
    indicators?.preview
      ? { key: "preview", label: "preview", state: indicators.preview.state, title: indicators.preview.message }
      : null
  ].filter(Boolean);
}

function App() {
  const [health, setHealth] = useState({ state: "loading", status: null, error: null });
  const [info, setInfo] = useState(fallbackInfo);
  const [source, setSource] = useState(null);
  const [sourceForm, setSourceForm] = useState(emptySourceForm);
  const [tree, setTree] = useState([]);
  const [files, setFiles] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [conversionProfiles, setConversionProfiles] = useState([]);
  const [selectedJobId, setSelectedJobId] = useState(null);
  const [selectedJob, setSelectedJob] = useState(null);
  const [jobItems, setJobItems] = useState([]);
  const [jobEvents, setJobEvents] = useState([]);
  const [selectedDirectory, setSelectedDirectory] = useState("");
  const [selectedFileId, setSelectedFileId] = useState(null);
  const [selectedSettingsSection, setSelectedSettingsSection] = useState("source");
  const [previewVisible, setPreviewVisible] = useState(true);
  const [activeOverlay, setActiveOverlay] = useState(null);
  const [conversionDraft, setConversionDraft] = useState(null);
  const [previewSettings, setPreviewSettings] = useState(defaultPreviewSettings);
  const [previewPresets, setPreviewPresets] = useState([]);
  const [previewPresetName, setPreviewPresetName] = useState("");
  const [livePreview, setLivePreview] = useState(null);
  const [libraryPreview, setLibraryPreview] = useState(null);
  const [actionMessage, setActionMessage] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [testResult, setTestResult] = useState(null);
  const [isWorking, setIsWorking] = useState(false);

  const treeItems = useMemo(() => flattenTree(tree), [tree]);
  const selectedFile = files.find((file) => file.id === selectedFileId) ?? files[0] ?? null;
  const liveSourceLabel = source?.name ?? info.active_source?.name ?? "No active source";
  const liveSourceMeta = source
    ? `${source.protocol.toUpperCase()} - ${source.host} - ${source.root_path}`
    : "Configure one active source to enable scan and browsing";
  const queueSummary = `${info.queue.running_jobs} running - ${info.queue.queued_jobs} queued`;
  const backendLabel =
    health.state === "ready"
      ? `Backend ${health.status}`
      : health.state === "loading"
        ? "Connecting backend"
        : "Backend offline";

  useEffect(() => {
    loadBootstrap();
  }, []);

  useEffect(() => {
    if (!files.length) {
      if (selectedFileId !== null) {
        setSelectedFileId(null);
      }
      return;
    }

    if (!selectedFileId || !files.some((file) => file.id === selectedFileId)) {
      setSelectedFileId(files[0].id);
    }
  }, [files, selectedFileId]);

  useEffect(() => {
    if (activeOverlay !== "jobs") {
      return undefined;
    }

    refreshJobsOverlay();
    const intervalId = window.setInterval(() => {
      refreshJobsOverlay(selectedJobId);
    }, 3000);
    return () => window.clearInterval(intervalId);
  }, [activeOverlay, selectedJobId]);

  useEffect(() => {
    if (activeOverlay !== "jobs" || !selectedJobId) {
      return undefined;
    }

    const eventSource = new EventSource(`/api/logs/stream?job_id=${encodeURIComponent(selectedJobId)}`);
    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        setJobEvents((current) => {
          if (current.some((entry) => entry.stream_id === payload.stream_id)) {
            return current;
          }
          return [...current, payload].slice(-200);
        });
      } catch {
        return;
      }
    };
    return () => eventSource.close();
  }, [activeOverlay, selectedJobId]);

  useEffect(() => {
    if (activeOverlay !== "settings" || selectedSettingsSection !== "preview") {
      return;
    }

    loadPreviewSettings();
  }, [activeOverlay, selectedSettingsSection]);

  useEffect(() => {
    if (!previewVisible || !source) {
      setLibraryPreview(null);
      return;
    }

    loadLibraryPreview();
  }, [previewVisible, source, selectedFileId, selectedDirectory, files]);

  useEffect(() => {
    if (activeOverlay !== "settings" || selectedSettingsSection !== "preview") {
      return undefined;
    }

    const timeoutId = window.setTimeout(async () => {
      try {
        const payload = await generateLivePreview(previewSettings);
        setLivePreview(payload.preview);
      } catch (error) {
        setActionError(error.message);
      }
    }, 180);

    return () => window.clearTimeout(timeoutId);
  }, [activeOverlay, selectedSettingsSection, previewSettings]);

  async function loadBootstrap(preferredDirectory = "", preserveForm = false) {
    try {
      const payload = await loadAppShellData();
      setHealth({ state: "ready", status: payload.health.status, error: null });
      setInfo(payload.info);
      setSource(payload.source);
      if (!preserveForm) {
        setSourceForm(toSourceForm(payload.source));
      }

      if (!payload.source) {
        setTree([]);
        setFiles([]);
        setJobs([]);
        setSelectedDirectory("");
        setLibraryPreview(null);
        return;
      }

      const [treePayload, jobsPayload] = await Promise.all([fetchTree(), fetchJobs()]);
      const flatNodes = flattenTree(treePayload.tree);
      const nextDirectory = flatNodes.some((node) => node.path === preferredDirectory) ? preferredDirectory : "";
      const filesPayload = await fetchFiles(nextDirectory);

      setTree(treePayload.tree);
      setJobs(jobsPayload.jobs);
      setFiles(filesPayload.files);
      setSelectedDirectory(nextDirectory);
    } catch (error) {
      setHealth({ state: "error", status: null, error: error.message });
    }
  }

  async function refreshLibrary(preferredDirectory = selectedDirectory) {
    await loadBootstrap(preferredDirectory, true);
  }

  async function refreshJobsOverlay(preferredJobId = selectedJobId) {
    const jobsPayload = await fetchJobs(50);
    setJobs(jobsPayload.jobs);
    const nextJobId =
      preferredJobId && jobsPayload.jobs.some((job) => job.id === preferredJobId)
        ? preferredJobId
        : jobsPayload.jobs[0]?.id ?? null;
    setSelectedJobId(nextJobId);
    if (!nextJobId) {
      setSelectedJob(null);
      setJobItems([]);
      setJobEvents([]);
      return;
    }

    const [jobPayload, itemsPayload, eventsPayload] = await Promise.all([
      fetchJob(nextJobId),
      fetchJobItems(nextJobId),
      fetchLogs({ jobId: nextJobId, limit: 200 })
    ]);
    setSelectedJob(jobPayload.job);
    setJobItems(itemsPayload.items);
    setJobEvents(eventsPayload.events);
  }

  async function loadPreviewSettings() {
    try {
      const [settingsPayload, presetsPayload] = await Promise.all([fetchSettings(), fetchPreviewLayouts()]);
      const nextSettings = settingsPayload.settings?.preview ?? defaultPreviewSettings;
      setPreviewSettings(nextSettings);
      setPreviewPresets(presetsPayload.presets);
      const selectedPreset = presetsPayload.presets.find((preset) => preset.id === nextSettings.layout_preset_id);
      setPreviewPresetName(selectedPreset?.name ?? "");
    } catch (error) {
      setActionError(error.message);
    }
  }

  async function loadLibraryPreview(fileId = selectedFile?.id, directoryPath = selectedDirectory) {
    if (!source) {
      return;
    }

    try {
      if (fileId) {
        const filePayload = await fetchFilePreview(fileId);
        if (filePayload.preview) {
          setLibraryPreview({ scope: "file", ...filePayload.preview });
          return;
        }
      }
      const directoryPayload = await fetchDirectoryPreview(directoryPath);
      setLibraryPreview(directoryPayload.preview ? { scope: "directory", ...directoryPayload.preview } : null);
    } catch (error) {
      setLibraryPreview(null);
      if (!String(error.message).includes("not available")) {
        setActionError(error.message);
      }
    }
  }

  function updateSourceField(field, value) {
    setSourceForm((current) => ({ ...current, [field]: value }));
  }

  function updatePreviewSetting(field, value) {
    setPreviewSettings((current) => ({ ...current, [field]: value }));
  }

  async function handleSourceTest() {
    setIsWorking(true);
    setActionError(null);
    setActionMessage(null);
    setTestResult(null);
    try {
      const result = await testSourceConnection(toSourcePayload(sourceForm));
      setTestResult(result);
      setActionMessage(result.message);
    } catch (error) {
      setActionError(error.message);
    } finally {
      setIsWorking(false);
    }
  }

  async function handleSourceSave() {
    setIsWorking(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const payload = await saveSource(toSourcePayload(sourceForm));
      setSource(payload.source);
      setSourceForm(toSourceForm(payload.source));
      setActionMessage("Source settings saved.");
      await refreshLibrary("");
    } catch (error) {
      setActionError(error.message);
    } finally {
      setIsWorking(false);
    }
  }

  async function handleReconnect() {
    setIsWorking(true);
    setActionError(null);
    setActionMessage(null);
    setTestResult(null);
    try {
      const result = await reconnectSource();
      setTestResult(result);
      setActionMessage(result.message);
      await refreshLibrary(selectedDirectory);
    } catch (error) {
      setActionError(error.message);
    } finally {
      setIsWorking(false);
    }
  }

  async function handleScanSource() {
    setIsWorking(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const payload = await createScanSourceJob();
      setActionMessage(payload.job.summary_message);
      await refreshLibrary(selectedDirectory);
    } catch (error) {
      setActionError(error.message);
    } finally {
      setIsWorking(false);
    }
  }

  async function handleRescanDirectory() {
    setIsWorking(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const payload = await createRescanDirectoryJob(selectedDirectory);
      setActionMessage(payload.job.summary_message);
      await refreshLibrary(selectedDirectory);
    } catch (error) {
      setActionError(error.message);
    } finally {
      setIsWorking(false);
    }
  }

  async function handleDirectoryJob(createJob) {
    setIsWorking(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const payload = await createJob(selectedDirectory);
      setActionMessage(payload.job.summary_message);
      await refreshLibrary(selectedDirectory);
      await loadLibraryPreview(selectedFile?.id, selectedDirectory);
      if (activeOverlay === "jobs") {
        await refreshJobsOverlay(payload.job.id);
      }
    } catch (error) {
      setActionError(error.message);
    } finally {
      setIsWorking(false);
    }
  }

  async function handleFilePreviewJob() {
    if (!selectedFile) {
      return;
    }

    setIsWorking(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const payload = await createPreviewFileJob(selectedFile.id);
      setActionMessage(payload.job.summary_message);
      await refreshLibrary(selectedDirectory);
      await loadLibraryPreview(selectedFile.id, selectedDirectory);
      if (activeOverlay === "jobs") {
        await refreshJobsOverlay(payload.job.id);
      }
    } catch (error) {
      setActionError(error.message);
    } finally {
      setIsWorking(false);
    }
  }

  async function handleSavePreviewSettings() {
    setIsWorking(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const payload = await saveSettings({ preview: previewSettings });
      setPreviewSettings(payload.settings.preview);
      setActionMessage("Preview settings saved.");
    } catch (error) {
      setActionError(error.message);
    } finally {
      setIsWorking(false);
    }
  }

  function handleLoadPreset() {
    const preset = previewPresets.find((entry) => entry.id === previewSettings.layout_preset_id);
    if (!preset) {
      return;
    }
    setPreviewSettings({
      sample_count: preset.sample_count,
      large_tile_count: preset.large_tile_count,
      timeline_flow: preset.timeline_flow,
      identity_diversity_enabled: preset.identity_diversity_enabled,
      layout_preset_id: preset.id
    });
    setPreviewPresetName(preset.name);
  }

  async function handleSavePreset(mode = "create") {
    setIsWorking(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const payload = {
        name: previewPresetName.trim() || "Custom preset",
        sample_count: previewSettings.sample_count,
        large_tile_count: previewSettings.large_tile_count,
        timeline_flow: previewSettings.timeline_flow,
        identity_diversity_enabled: previewSettings.identity_diversity_enabled,
        layout_definition: { kind: "auto-grid", version: 1 }
      };
      const response =
        mode === "update" && previewSettings.layout_preset_id && previewSettings.layout_preset_id !== "default-preview-grid"
          ? await updatePreviewLayout(previewSettings.layout_preset_id, payload)
          : await createPreviewLayout(payload);
      const savedPreset = response.preset;
      setPreviewSettings((current) => ({ ...current, layout_preset_id: savedPreset.id }));
      setPreviewPresetName(savedPreset.name);
      const presetsPayload = await fetchPreviewLayouts();
      setPreviewPresets(presetsPayload.presets);
      setActionMessage(mode === "update" ? "Preview preset updated." : "Preview preset saved.");
    } catch (error) {
      setActionError(error.message);
    } finally {
      setIsWorking(false);
    }
  }

  async function ensureConversionProfiles() {
    if (conversionProfiles.length) {
      return conversionProfiles;
    }
    const payload = await fetchConversionProfiles();
    setConversionProfiles(payload.profiles);
    return payload.profiles;
  }

  async function openConvertDialog(scope) {
    setActionError(null);
    try {
      const profiles = await ensureConversionProfiles();
      const defaultProfile = profiles.find((profile) => profile.is_default) ?? profiles[0] ?? null;
      if (!defaultProfile) {
        throw new Error("No saved conversion profiles are available.");
      }

      setConversionDraft({
        scope,
        fileId: scope === "file" ? selectedFile?.id ?? null : null,
        relativePath: selectedDirectory,
        fileName: scope === "file" ? selectedFile?.file_name ?? "" : "",
        profileId: defaultProfile.id,
        mode: "production"
      });
      setActiveOverlay("convert");
    } catch (error) {
      setActionError(error.message);
    }
  }

  function updateConversionDraft(field, value) {
    setConversionDraft((current) => (current ? { ...current, [field]: value } : current));
  }

  async function submitConversionJob() {
    if (!conversionDraft) {
      return;
    }

    setIsWorking(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const payload =
        conversionDraft.scope === "file"
          ? await createConvertFileJob(conversionDraft.fileId, {
              profileId: conversionDraft.profileId,
              mode: conversionDraft.mode
            })
          : await createConvertDirectoryJob(conversionDraft.relativePath, {
              profileId: conversionDraft.profileId,
              mode: conversionDraft.mode
            });
      setActionMessage(payload.job.summary_message);
      setActiveOverlay(null);
      setConversionDraft(null);
      await refreshLibrary(selectedDirectory);
      if (activeOverlay === "jobs") {
        await refreshJobsOverlay(payload.job.id);
      }
    } catch (error) {
      setActionError(error.message);
    } finally {
      setIsWorking(false);
    }
  }

  async function openJobsOverlay() {
    setActiveOverlay("jobs");
    setActionError(null);
    try {
      await refreshJobsOverlay();
    } catch (error) {
      setActionError(error.message);
    }
  }

  async function handleCancelJob(jobId) {
    setActionError(null);
    try {
      const payload = await cancelJob(jobId);
      setActionMessage(payload.job.summary_message);
      await refreshLibrary(selectedDirectory);
      await refreshJobsOverlay(jobId);
    } catch (error) {
      setActionError(error.message);
    }
  }

  async function handleRestartJob(jobId) {
    setActionError(null);
    try {
      const payload = await restartJob(jobId);
      setActionMessage(payload.job.summary_message);
      await refreshLibrary(selectedDirectory);
      await refreshJobsOverlay(payload.job.id);
    } catch (error) {
      setActionError(error.message);
    }
  }

  async function handleSelectDirectory(path) {
    setActionError(null);
    try {
      const payload = await fetchFiles(path);
      setFiles(payload.files);
      setSelectedDirectory(path);
    } catch (error) {
      setActionError(error.message);
    }
  }

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
            Browse one active source, run conversion and preview jobs independently, and tune
            preview sampling and large-tile selection from a dedicated settings screen with live
            layout feedback.
          </p>
          {health.error ? <p className="muted">Last backend error: {health.error}</p> : null}
          {actionError ? <p className="feedback error">{actionError}</p> : null}
          {actionMessage ? <p className="feedback">{actionMessage}</p> : null}
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
            <button
              type="button"
              className="ghost-button"
              disabled={!source || isWorking}
              onClick={handleScanSource}
            >
              Scan source
            </button>
            <button type="button" className="ghost-button" onClick={openJobsOverlay}>
              Jobs
            </button>
            <button
              type="button"
              className="primary-button"
              onClick={() => {
                setSelectedSettingsSection("preview");
                setActiveOverlay("settings");
              }}
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
            <button
              type="button"
              className="mini-button"
              disabled={!source || isWorking}
              onClick={handleScanSource}
            >
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
                    onClick={() => handleSelectDirectory(node.path)}
                  >
                    <span>{node.path ? node.name : "Source root"}</span>
                    <span className="tree-badges">
                      {badges.map((badge) => (
                        <span
                          key={badge.key}
                          className={`tree-badge tree-badge-${badge.state}`}
                          title={badge.title}
                        >
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

        <section className="panel file-panel">
          <div className="panel-header">
            <div>
              <p className="section-kicker">Current folder</p>
              <h2>{formatDirectoryLabel(selectedDirectory)}</h2>
            </div>
            <div className="inline-actions">
              <button
                type="button"
                className="mini-button"
                disabled={!source || isWorking}
                onClick={() => openConvertDialog("directory")}
              >
                Convert subtree
              </button>
              <button
                type="button"
                className="mini-button"
                disabled={!source || !selectedFile || isWorking}
                onClick={() => openConvertDialog("file")}
              >
                Convert file
              </button>
              <button
                type="button"
                className="mini-button"
                disabled={!source || !selectedFile || isWorking}
                onClick={handleFilePreviewJob}
              >
                Preview file
              </button>
              <button
                type="button"
                className="mini-button"
                disabled={!source || isWorking}
                onClick={() => handleDirectoryJob(createPreviewDirectoryJob)}
              >
                Preview subtree
              </button>
              <button
                type="button"
                className="mini-button"
                disabled={!source || isWorking}
                onClick={() => handleDirectoryJob(createTagDirectoryJob)}
              >
                Tag subtree
              </button>
              <button
                type="button"
                className="mini-button"
                disabled={!source || isWorking}
                onClick={handleRescanDirectory}
              >
                Rescan subtree
              </button>
            </div>
          </div>

          <div className="list-header">
            <span>Name</span>
            <span>Type</span>
            <span>Size</span>
            <span>Modified</span>
            <span>Status</span>
          </div>

          <div className="file-list">
            {files.length ? (
              files.map((file) => (
                <article
                  key={file.id}
                  className={`file-row ${selectedFile?.id === file.id ? "active" : ""}`}
                  onClick={() => setSelectedFileId(file.id)}
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
                      Convert {formatStatusLabel(file.conversion_state)}
                    </span>
                    <span className={`state-pill state-${file.preview_state}`}>
                      Preview {formatStatusLabel(file.preview_state)}
                    </span>
                  </div>
                </article>
              ))
            ) : (
              <div className="empty-state">
                <h3>No files in this folder</h3>
                <p>
                  This folder either has no files yet or has not been discovered by a completed
                  scan.
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
                <h2>{libraryPreview?.scope === "directory" ? "Directory collage" : "Selected asset"}</h2>
              </div>
              <button
                type="button"
                className="mini-button"
                onClick={() => {
                  setSelectedSettingsSection("preview");
                  setActiveOverlay("settings");
                }}
              >
                Preview settings
              </button>
            </div>

            <div className="preview-card">
              <div className="preview-canvas">
                {libraryPreview?.image_data_url ? (
                  <img
                    className="preview-image"
                    src={libraryPreview.image_data_url}
                    alt="Generated preview collage"
                  />
                ) : (
                  <span>No preview asset yet. Run a file or subtree preview job.</span>
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
                    ? `${libraryPreview.metadata.sample_count} sampled frames with ${libraryPreview.metadata.large_tile_count} large tiles in ${libraryPreview.metadata.timeline_flow} flow.`
                    : "Preview generation is on-demand and stays independent from conversion."}
                </p>
              </div>
            </div>

            <dl className="meta-list">
              <div>
                <dt>Selected folder</dt>
                <dd>{formatDirectoryLabel(selectedDirectory)}</dd>
              </div>
              <div>
                <dt>Visible files</dt>
                <dd>{files.length}</dd>
              </div>
              <div>
                <dt>Selected file</dt>
                <dd>{selectedFile?.file_name ?? "-"}</dd>
              </div>
              <div>
                <dt>Sample count</dt>
                <dd>{libraryPreview?.metadata?.sample_count ?? "-"}</dd>
              </div>
              <div>
                <dt>Active source</dt>
                <dd>{liveSourceLabel}</dd>
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
                <h2>Recent jobs</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => setActiveOverlay(null)}>
                Close
              </button>
            </div>
            <div className="jobs-grid">
              {jobs.length ? (
                <>
                  <div className="job-list">
                    {jobs.map((job) => (
                      <button
                        key={job.id}
                        type="button"
                        className={`job-card job-select-card ${selectedJobId === job.id ? "active" : ""}`}
                        onClick={() => refreshJobsOverlay(job.id)}
                      >
                        <div className="job-header">
                          <strong>{formatJobTypeLabel(job.job_type)}</strong>
                          <span className={`state-pill state-${job.status}`}>{job.status}</span>
                        </div>
                        <p>{formatJobScope(job)}</p>
                        <p className="muted">{job.summary_message || "No summary available."}</p>
                        <p className="muted">
                          Items {job.item_counts.completed}/{job.item_counts.total}
                        </p>
                      </button>
                    ))}
                  </div>
                  <section className="job-detail panel">
                    {selectedJob ? (
                      <>
                        <div className="job-detail-header">
                          <div>
                            <p className="section-kicker">Job detail</p>
                            <h3>
                              {formatJobTypeLabel(selectedJob.job_type)} · {formatJobScope(selectedJob)}
                            </h3>
                          </div>
                          <div className="inline-actions">
                            <button type="button" className="ghost-button" onClick={() => refreshJobsOverlay(selectedJob.id)}>
                              Refresh
                            </button>
                            <button
                              type="button"
                              className="ghost-button"
                              disabled={!["queued", "running"].includes(selectedJob.status)}
                              onClick={() => handleCancelJob(selectedJob.id)}
                            >
                              Cancel
                            </button>
                            <button
                              type="button"
                              className="ghost-button"
                              disabled={!["completed", "failed", "cancelled"].includes(selectedJob.status)}
                              onClick={() => handleRestartJob(selectedJob.id)}
                            >
                              Restart
                            </button>
                          </div>
                        </div>
                        <div className="job-meta-grid">
                          <div>
                            <span className="muted">Status</span>
                            <strong>{selectedJob.status}</strong>
                          </div>
                          <div>
                            <span className="muted">Queued</span>
                            <strong>{selectedJob.item_counts.queued}</strong>
                          </div>
                          <div>
                            <span className="muted">Running</span>
                            <strong>{selectedJob.item_counts.running}</strong>
                          </div>
                          <div>
                            <span className="muted">Completed</span>
                            <strong>{selectedJob.item_counts.completed}</strong>
                          </div>
                          <div>
                            <span className="muted">Failed</span>
                            <strong>{selectedJob.item_counts.failed}</strong>
                          </div>
                          <div>
                            <span className="muted">Cancelled</span>
                            <strong>{selectedJob.item_counts.cancelled}</strong>
                          </div>
                        </div>
                        <p className="muted">{selectedJob.summary_message || "No summary available."}</p>
                        <div className="job-items-block">
                          <h4>Items</h4>
                          <div className="job-items-list">
                            {jobItems.map((item) => (
                              <article key={item.id} className="job-item-row">
                                <div>
                                  <strong>{item.file_name || item.item_key || "Scope item"}</strong>
                                  <p className="row-subtitle">{item.relative_path || item.message || "-"}</p>
                                </div>
                                <span className={`state-pill state-${item.status}`}>{item.status}</span>
                              </article>
                            ))}
                          </div>
                        </div>
                        <div className="job-events-block">
                          <h4>Events</h4>
                          <pre className="log-console">
                            {jobEvents.length
                              ? jobEvents
                                  .map(
                                    (event) =>
                                      `${formatDate(event.created_at)}  ${event.level.toUpperCase()}  ${event.message}`
                                  )
                                  .join("\n")
                              : "No events yet."}
                          </pre>
                        </div>
                      </>
                    ) : (
                      <div className="empty-state compact">
                        <h3>No job selected</h3>
                        <p>Select a job to inspect its items and event stream.</p>
                      </div>
                    )}
                  </section>
                </>
              ) : (
                <div className="empty-state compact">
                  <h3>No jobs yet</h3>
                  <p>Queued scan, rescan, convert, preview, tag, and tune jobs will appear here.</p>
                </div>
              )}
            </div>
          </section>
        </div>
      ) : null}

      {activeOverlay === "convert" && conversionDraft ? (
        <div className="overlay-backdrop" onClick={() => setActiveOverlay(null)}>
          <section className="overlay panel modal-shell convert-shell" onClick={(event) => event.stopPropagation()}>
            <div className="panel-header">
              <div>
                <p className="section-kicker">Conversion</p>
                <h2>{conversionDraft.scope === "file" ? "Selected file" : "Selected folder"}</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => setActiveOverlay(null)}>
                Close
              </button>
            </div>

            <div className="convert-layout">
              <div className="note-card">
                <strong>
                  {conversionDraft.scope === "file"
                    ? conversionDraft.fileName || "Selected file"
                    : formatDirectoryLabel(conversionDraft.relativePath)}
                </strong>
                <p>
                  Production mode writes a temp file, validates it quickly, and replaces the
                  source only on success. Test mode writes a separate output and preserves the
                  source file.
                </p>
              </div>

              <div className="form-grid">
                <label className="full-width">
                  <span>Saved profile</span>
                  <select
                    value={conversionDraft.profileId}
                    onChange={(event) => updateConversionDraft("profileId", event.target.value)}
                  >
                    {conversionProfiles.map((profile) => (
                      <option key={profile.id} value={profile.id}>
                        {formatProfileLabel(profile)}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  <span>Mode</span>
                  <select
                    value={conversionDraft.mode}
                    onChange={(event) => updateConversionDraft("mode", event.target.value)}
                  >
                    <option value="production">Production replace source</option>
                    <option value="test">Test keep source</option>
                  </select>
                </label>
              </div>

              <div className="inline-actions">
                <button type="button" className="ghost-button" onClick={() => setActiveOverlay(null)}>
                  Cancel
                </button>
                <button type="button" className="primary-button" disabled={isWorking} onClick={submitConversionJob}>
                  Start conversion
                </button>
              </div>
            </div>
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
                <h2>{settingsSections.find((section) => section.id === selectedSettingsSection)?.label}</h2>
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
                {selectedSettingsSection === "source" ? (
                  <div className="source-settings">
                    <p>
                      Video Archive supports one active source at a time. Test connectivity, save the
                      source, then scan it to populate the library tree.
                    </p>
                    <div className="form-grid">
                      <label>
                        <span>Name</span>
                        <input
                          value={sourceForm.name}
                          onChange={(event) => updateSourceField("name", event.target.value)}
                        />
                      </label>
                      <label>
                        <span>Protocol</span>
                        <select
                          value={sourceForm.protocol}
                          onChange={(event) => updateSourceField("protocol", event.target.value)}
                        >
                          <option value="smb">SMB</option>
                          <option value="ftp">FTP</option>
                          <option value="sftp">SFTP</option>
                          <option value="webdav">WebDAV</option>
                        </select>
                      </label>
                      <label>
                        <span>Host</span>
                        <input
                          value={sourceForm.host}
                          onChange={(event) => updateSourceField("host", event.target.value)}
                        />
                      </label>
                      <label>
                        <span>Port</span>
                        <input
                          value={sourceForm.port}
                          onChange={(event) => updateSourceField("port", event.target.value)}
                          placeholder="Default"
                        />
                      </label>
                      <label className="full-width">
                        <span>Root path</span>
                        <input
                          value={sourceForm.root_path}
                          onChange={(event) => updateSourceField("root_path", event.target.value)}
                          placeholder="Accessible path or UNC share"
                        />
                      </label>
                      <label>
                        <span>Username</span>
                        <input
                          value={sourceForm.username}
                          onChange={(event) => updateSourceField("username", event.target.value)}
                        />
                      </label>
                      <label>
                        <span>Password</span>
                        <input
                          type="password"
                          value={sourceForm.password}
                          onChange={(event) => updateSourceField("password", event.target.value)}
                          placeholder={source?.has_password ? "Leave blank to keep saved password" : ""}
                        />
                      </label>
                    </div>

                    <div className="inline-actions">
                      <button type="button" className="ghost-button" disabled={isWorking} onClick={handleSourceTest}>
                        Test connection
                      </button>
                      <button type="button" className="ghost-button" disabled={!source || isWorking} onClick={handleReconnect}>
                        Reconnect
                      </button>
                      <button type="button" className="ghost-button" disabled={!source || isWorking} onClick={handleScanSource}>
                        Scan source
                      </button>
                      <button type="button" className="primary-button" disabled={isWorking} onClick={handleSourceSave}>
                        Save source
                      </button>
                    </div>

                    {testResult ? (
                      <div className={`note-card ${testResult.ok ? "note-card-success" : "note-card-warning"}`}>
                        <strong>{testResult.ok ? "Ready to scan" : "Connection partial"}</strong>
                        <p>{testResult.message}</p>
                        <p className="muted">
                          {testResult.host}:{testResult.port} - {testResult.root_path}
                        </p>
                      </div>
                    ) : null}
                  </div>
                ) : selectedSettingsSection === "preview" ? (
                  <div className="source-settings">
                    <p>
                      Preview generation stays independent from conversion. Save the sampling and
                      large-tile rules here, then use the live preview to inspect the layout before
                      launching jobs.
                    </p>
                    <div className="form-grid">
                      <label>
                        <span>Sample count</span>
                        <input
                          type="number"
                          min="3"
                          max="24"
                          value={previewSettings.sample_count}
                          onChange={(event) => updatePreviewSetting("sample_count", Number(event.target.value))}
                        />
                      </label>
                      <label>
                        <span>Large tile count</span>
                        <input
                          type="number"
                          min="0"
                          max="6"
                          value={previewSettings.large_tile_count}
                          onChange={(event) => updatePreviewSetting("large_tile_count", Number(event.target.value))}
                        />
                      </label>
                      <label>
                        <span>Timeline flow</span>
                        <select
                          value={previewSettings.timeline_flow}
                          onChange={(event) => updatePreviewSetting("timeline_flow", event.target.value)}
                        >
                          <option value="row">Row by row</option>
                          <option value="column">Column by column</option>
                          <option value="shuffle">Shuffled time order</option>
                        </select>
                      </label>
                      <label className="toggle-row">
                        <span>Identity diversity</span>
                        <input
                          type="checkbox"
                          checked={previewSettings.identity_diversity_enabled}
                          onChange={(event) => updatePreviewSetting("identity_diversity_enabled", event.target.checked)}
                        />
                      </label>
                      <label className="full-width">
                        <span>Saved preset</span>
                        <select
                          value={previewSettings.layout_preset_id}
                          onChange={(event) => updatePreviewSetting("layout_preset_id", event.target.value)}
                        >
                          {previewPresets.map((preset) => (
                            <option key={preset.id} value={preset.id}>
                              {preset.name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="full-width">
                        <span>Preset name</span>
                        <input
                          value={previewPresetName}
                          onChange={(event) => setPreviewPresetName(event.target.value)}
                          placeholder="Balanced Grid"
                        />
                      </label>
                    </div>

                    <div className="inline-actions">
                      <button type="button" className="ghost-button" disabled={isWorking} onClick={handleLoadPreset}>
                        Load preset
                      </button>
                      <button type="button" className="ghost-button" disabled={isWorking} onClick={() => handleSavePreset("create")}>
                        Save as new preset
                      </button>
                      <button
                        type="button"
                        className="ghost-button"
                        disabled={isWorking || previewSettings.layout_preset_id === "default-preview-grid"}
                        onClick={() => handleSavePreset("update")}
                      >
                        Update preset
                      </button>
                      <button type="button" className="primary-button" disabled={isWorking} onClick={handleSavePreviewSettings}>
                        Save preview settings
                      </button>
                    </div>

                    <div className="preview-settings-grid">
                      <div className="note-card">
                        <strong>Selection rules</strong>
                        <p>
                          First two large tiles prefer faces. Remaining large tiles prefer human
                          figures. When identity diversity is enabled, the backend falls back to
                          separate timeline regions if a full identity pass is too expensive.
                        </p>
                      </div>
                      <div className="note-card preview-layout-card">
                        <strong>Live preview</strong>
                        {livePreview?.image_data_url ? (
                          <img className="preview-image" src={livePreview.image_data_url} alt="Live preview layout" />
                        ) : (
                          <div className="settings-placeholder compact-placeholder">
                            <span>Generating layout preview...</span>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="settings-placeholder">
                    <span>This settings section stays out of scope for the current browsing flow.</span>
                  </div>
                )}
              </section>
            </div>
          </section>
        </div>
      ) : null}
    </main>
  );
}

export default App;
