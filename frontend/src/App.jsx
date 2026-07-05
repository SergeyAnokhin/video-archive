import { useEffect, useMemo, useState } from "react";
import {
  cancelJob,
  createConvertDirectoryJob,
  createConvertFileJob,
  createPreviewDirectoryJob,
  createPreviewFileJob,
  createTagFileJob,
  createTuneFileJob,
  createRescanDirectoryJob,
  createScanSourceJob,
  createTagDirectoryJob,
  createPreviewLayout,
  fallbackInfo,
  fetchDirectoryPreview,
  fetchFileDetail,
  fetchFilePlayback,
  fetchFilePreview,
  fetchFileTags,
  fetchJob,
  fetchJobItems,
  fetchFiles,
  fetchJobs,
  fetchLogs,
  fetchPlaybackSettings,
  fetchPreviewLayouts,
  fetchProviderSettings,
  fetchSettings,
  fetchTree,
  fetchConversionProfiles,
  generateLivePreview,
  loadAppShellData,
  promoteTuneVariant,
  reconnectSource,
  restartJob,
  savePlaybackSettings,
  saveProviderSettings,
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

const defaultTaggingSettings = {
  provider: "openrouter",
  sample_count: 9,
  combine_frames: true,
  prefer_batch: true,
  vocabulary: []
};

const defaultPlaybackSettings = {
  mode: "embedded"
};

const defaultProviderSettings = [
  { provider: "openrouter", enabled: false, vision_model: "", text_model: "", prefer_batch: true, api_key: "", api_key_configured: false },
  { provider: "gemini", enabled: false, vision_model: "gemini-2.0-flash", text_model: "", prefer_batch: true, api_key: "", api_key_configured: false },
  { provider: "fal", enabled: false, vision_model: "", text_model: "", prefer_batch: true, api_key: "", api_key_configured: false },
  { provider: "mistral", enabled: false, vision_model: "pixtral-large-latest", text_model: "", prefer_batch: true, api_key: "", api_key_configured: false }
];

function toTaggingForm(settings) {
  return {
    ...defaultTaggingSettings,
    ...settings,
    vocabulary: Array.isArray(settings?.vocabulary)
      ? settings.vocabulary.map((entry) => (typeof entry === "string" ? entry : entry.display_name)).filter(Boolean)
      : []
  };
}

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

function formatConfidence(value) {
  if (!Number.isFinite(value)) {
    return "-";
  }
  return `${Math.round(value * 100)}%`;
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
  const [taggingSettings, setTaggingSettings] = useState(defaultTaggingSettings);
  const [providerSettings, setProviderSettings] = useState(defaultProviderSettings);
  const [playbackSettings, setPlaybackSettings] = useState(defaultPlaybackSettings);
  const [previewPresets, setPreviewPresets] = useState([]);
  const [previewPresetName, setPreviewPresetName] = useState("");
  const [livePreview, setLivePreview] = useState(null);
  const [libraryPreview, setLibraryPreview] = useState(null);
  const [selectedFileTags, setSelectedFileTags] = useState(null);
  const [actionMessage, setActionMessage] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [testResult, setTestResult] = useState(null);
  const [isWorking, setIsWorking] = useState(false);
  const [fileDetail, setFileDetail] = useState(null);
  const [playbackTarget, setPlaybackTarget] = useState(null);
  const [logFilterJobId, setLogFilterJobId] = useState("");
  const [logFilterFileId, setLogFilterFileId] = useState("");
  const [logFilterLevel, setLogFilterLevel] = useState("");
  const [liveLogEvents, setLiveLogEvents] = useState([]);
  const [tuneDraft, setTuneDraft] = useState(null);
  const [tuneJob, setTuneJob] = useState(null);
  const [tuneItems, setTuneItems] = useState([]);
  const [promoteDraft, setPromoteDraft] = useState(null);

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
    if (activeOverlay !== "tune" || !tuneJob || ["completed", "failed", "cancelled"].includes(tuneJob.status)) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      refreshTuneJob(tuneJob.id);
    }, 2000);
    return () => window.clearInterval(intervalId);
  }, [activeOverlay, tuneJob?.id, tuneJob?.status]);

  useEffect(() => {
    if (activeOverlay !== "logs") {
      return undefined;
    }

    const params = new URLSearchParams();
    if (logFilterJobId) {
      params.set("job_id", logFilterJobId);
    }
    if (logFilterFileId) {
      params.set("file_id", logFilterFileId);
    }
    if (logFilterLevel) {
      params.set("level", logFilterLevel);
    }
    const query = params.toString();

    fetchLogs({ jobId: logFilterJobId || undefined, limit: 150 })
      .then((payload) => setLiveLogEvents(payload.events))
      .catch((error) => setActionError(error.message));

    const eventSource = new EventSource(`/api/logs/stream${query ? `?${query}` : ""}`);
    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        setLiveLogEvents((current) => {
          if (current.some((entry) => entry.stream_id === payload.stream_id)) {
            return current;
          }
          return [...current, payload].slice(-300);
        });
      } catch {
        return;
      }
    };
    return () => eventSource.close();
  }, [activeOverlay, logFilterJobId, logFilterFileId, logFilterLevel]);

  useEffect(() => {
    if (activeOverlay !== "settings" || !["preview", "tagging", "providers", "playback"].includes(selectedSettingsSection)) {
      return;
    }

    loadSettingsSection(selectedSettingsSection);
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

  useEffect(() => {
    if (!selectedFile?.id) {
      setSelectedFileTags(null);
      return;
    }
    loadSelectedFileTags(selectedFile.id);
  }, [selectedFile?.id]);

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

  async function loadSettingsSection(section) {
    try {
      if (section === "preview") {
        const [settingsPayload, presetsPayload] = await Promise.all([fetchSettings(), fetchPreviewLayouts()]);
        const nextSettings = settingsPayload.settings?.preview ?? defaultPreviewSettings;
        setPreviewSettings(nextSettings);
        setPreviewPresets(presetsPayload.presets);
        const selectedPreset = presetsPayload.presets.find((preset) => preset.id === nextSettings.layout_preset_id);
        setPreviewPresetName(selectedPreset?.name ?? "");
        return;
      }

      if (section === "tagging") {
        const settingsPayload = await fetchSettings();
        setTaggingSettings(toTaggingForm(settingsPayload.settings?.tagging ?? defaultTaggingSettings));
        return;
      }

      if (section === "providers") {
        const providersPayload = await fetchProviderSettings();
        setProviderSettings(
          defaultProviderSettings.map((base) => {
            const current = providersPayload.providers?.find((entry) => entry.provider === base.provider);
            return current ? { ...base, ...current, api_key: "" } : base;
          })
        );
        return;
      }

      if (section === "playback") {
        const playbackPayload = await fetchPlaybackSettings();
        setPlaybackSettings({ ...defaultPlaybackSettings, ...playbackPayload.settings });
      }
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

  async function loadSelectedFileTags(fileId) {
    try {
      const payload = await fetchFileTags(fileId);
      setSelectedFileTags(payload.tags);
    } catch (error) {
      setSelectedFileTags(null);
      if (!String(error.message).includes("does not exist")) {
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

  function updateTaggingSetting(field, value) {
    setTaggingSettings((current) => ({ ...current, [field]: value }));
  }

  function updateProviderSetting(providerName, field, value) {
    setProviderSettings((current) =>
      current.map((entry) => (entry.provider === providerName ? { ...entry, [field]: value } : entry))
    );
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

  async function handleFileTagJob() {
    if (!selectedFile) {
      return;
    }

    setIsWorking(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const payload = await createTagFileJob(selectedFile.id);
      setActionMessage(payload.job.summary_message);
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

  async function handleSaveTaggingSettings() {
    setIsWorking(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const payload = await saveSettings({
        tagging: {
          provider: taggingSettings.provider,
          sample_count: taggingSettings.sample_count,
          combine_frames: taggingSettings.combine_frames,
          prefer_batch: taggingSettings.prefer_batch,
          vocabulary: taggingSettings.vocabulary
        }
      });
      setTaggingSettings(toTaggingForm(payload.settings.tagging));
      setActionMessage("Tagging settings saved.");
    } catch (error) {
      setActionError(error.message);
    } finally {
      setIsWorking(false);
    }
  }

  async function handleSaveProviderSettings() {
    setIsWorking(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const payload = await saveProviderSettings(
        providerSettings.map((entry) => ({
          provider: entry.provider,
          enabled: entry.enabled,
          vision_model: entry.vision_model,
          text_model: entry.text_model,
          prefer_batch: entry.prefer_batch,
          api_key: entry.api_key
        }))
      );
      setProviderSettings(
        defaultProviderSettings.map((base) => {
          const current = payload.providers.find((entry) => entry.provider === base.provider);
          return current ? { ...base, ...current, api_key: "" } : base;
        })
      );
      setActionMessage("Provider settings saved.");
    } catch (error) {
      setActionError(error.message);
    } finally {
      setIsWorking(false);
    }
  }

  async function handleSavePlaybackSettings() {
    setIsWorking(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const payload = await savePlaybackSettings(playbackSettings);
      setPlaybackSettings({ ...defaultPlaybackSettings, ...payload.settings });
      setActionMessage("Playback settings saved.");
    } catch (error) {
      setActionError(error.message);
    } finally {
      setIsWorking(false);
    }
  }

  async function openFileDetailOverlay(file = selectedFile) {
    if (!file) {
      return;
    }
    setActionError(null);
    setFileDetail(null);
    setSelectedFileId(file.id);
    setActiveOverlay("fileDetail");
    try {
      const [detailPayload, tagsPayload] = await Promise.all([
        fetchFileDetail(file.id),
        fetchFileTags(file.id).catch(() => ({ tags: null }))
      ]);
      setFileDetail(detailPayload.file);
      setSelectedFileTags(tagsPayload.tags);
    } catch (error) {
      setActionError(error.message);
    }
  }

  async function openPlaybackOverlay(file = selectedFile) {
    if (!file) {
      return;
    }
    setActionError(null);
    setPlaybackTarget(null);
    setActiveOverlay("playback");
    try {
      const payload = await fetchFilePlayback(file.id);
      setPlaybackTarget({ file, ...payload.playback });
    } catch (error) {
      setActionError(error.message);
    }
  }

  function openLogViewerOverlay() {
    setLogFilterJobId(selectedJobId ?? "");
    setLogFilterFileId(selectedFile?.id ?? "");
    setLogFilterLevel("");
    setLiveLogEvents([]);
    setActiveOverlay("logs");
  }

  function openTuneOverlay(file = selectedFile) {
    if (!file) {
      return;
    }
    setActionError(null);
    setTuneJob(null);
    setTuneItems([]);
    setTuneDraft({
      fileId: file.id,
      fileName: file.file_name,
      dimensionValues: "1000, 900, 800",
      qualityValues: "",
      codecValues: ""
    });
    setActiveOverlay("tune");
  }

  function updateTuneDraft(field, value) {
    setTuneDraft((current) => (current ? { ...current, [field]: value } : current));
  }

  function parseCommaSeparatedInts(value) {
    return value
      .split(",")
      .map((entry) => entry.trim())
      .filter(Boolean)
      .map((entry) => Number(entry))
      .filter((entry) => Number.isFinite(entry) && entry > 0);
  }

  function parseCommaSeparatedStrings(value) {
    return value
      .split(",")
      .map((entry) => entry.trim())
      .filter(Boolean);
  }

  async function submitTuneJob() {
    if (!tuneDraft) {
      return;
    }
    setIsWorking(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const sweep = {
        dimension_values: parseCommaSeparatedInts(tuneDraft.dimensionValues),
        quality_values: parseCommaSeparatedStrings(tuneDraft.qualityValues),
        codec_values: parseCommaSeparatedStrings(tuneDraft.codecValues)
      };
      const payload = await createTuneFileJob(tuneDraft.fileId, sweep);
      setActionMessage(payload.job.summary_message);
      await refreshTuneJob(payload.job.id);
    } catch (error) {
      setActionError(error.message);
    } finally {
      setIsWorking(false);
    }
  }

  async function refreshTuneJob(jobId = tuneJob?.id) {
    if (!jobId) {
      return;
    }
    try {
      const [jobPayload, itemsPayload] = await Promise.all([fetchJob(jobId), fetchJobItems(jobId)]);
      setTuneJob(jobPayload.job);
      setTuneItems(itemsPayload.items);
    } catch (error) {
      setActionError(error.message);
    }
  }

  function openPromoteDialog(item) {
    setPromoteDraft({
      jobId: tuneJob.id,
      itemId: item.id,
      name: `Tuned ${item.variant_params?.label ?? item.item_key ?? "profile"}`,
      isDefault: false
    });
  }

  async function submitPromoteTuneVariant() {
    if (!promoteDraft) {
      return;
    }
    setIsWorking(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const payload = await promoteTuneVariant(promoteDraft);
      setActionMessage(`Saved conversion profile "${payload.profile.name}" from tuning result.`);
      setPromoteDraft(null);
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
            Browse one active source, run conversion, preview, and closed-vocabulary tagging jobs
            independently, and tune preview or tagging behavior from dedicated settings screens.
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
            <button type="button" className="ghost-button" onClick={openLogViewerOverlay}>
              Logs
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
                disabled={!source || !selectedFile}
                onClick={() => openFileDetailOverlay()}
              >
                Details
              </button>
              <button
                type="button"
                className="mini-button"
                disabled={!source || !selectedFile}
                onClick={() => openPlaybackOverlay()}
              >
                Play
              </button>
              <button
                type="button"
                className="mini-button"
                disabled={!source || !selectedFile}
                onClick={() => openTuneOverlay()}
              >
                Tune file
              </button>
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
                disabled={!source || !selectedFile || isWorking}
                onClick={handleFileTagJob}
              >
                Tag file
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
                  onDoubleClick={() => openFileDetailOverlay(file)}
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
                <dt>Assigned tags</dt>
                <dd>{selectedFileTags?.tags?.length ?? 0}</dd>
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

            <div className="note-card">
              <strong>Closed-vocabulary tags</strong>
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
                    {selectedFileTags.tagging_model_info?.provider ?? "-"} · {selectedFileTags.tagging_model_info?.model ?? "-"} ·{" "}
                    {selectedFileTags.tagging_updated_at ? formatDate(selectedFileTags.tagging_updated_at) : "-"}
                  </p>
                </>
              ) : (
                <p>No tags stored for the selected video yet. Run a file or subtree tagging job.</p>
              )}
            </div>
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

      {activeOverlay === "fileDetail" ? (
        <div className="overlay-backdrop" onClick={() => setActiveOverlay(null)}>
          <section className="overlay panel modal-shell" onClick={(event) => event.stopPropagation()}>
            <div className="panel-header">
              <div>
                <p className="section-kicker">Video details</p>
                <h2>{fileDetail?.file_name ?? selectedFile?.file_name ?? "Loading..."}</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => setActiveOverlay(null)}>
                Close
              </button>
            </div>

            {fileDetail ? (
              <div className="convert-layout">
                <div className="note-card">
                  <strong>Metadata summary</strong>
                  <dl className="meta-list">
                    <div>
                      <dt>Relative path</dt>
                      <dd>{fileDetail.relative_path}</dd>
                    </div>
                    <div>
                      <dt>Size</dt>
                      <dd>{formatBytes(fileDetail.size_bytes)}</dd>
                    </div>
                    <div>
                      <dt>Modified</dt>
                      <dd>{formatDate(fileDetail.modified_at)}</dd>
                    </div>
                    <div>
                      <dt>Conversion state</dt>
                      <dd>{formatStatusLabel(fileDetail.conversion_state)}</dd>
                    </div>
                    <div>
                      <dt>Last converted</dt>
                      <dd>{formatDate(fileDetail.last_converted_at)}</dd>
                    </div>
                    <div>
                      <dt>Preview state</dt>
                      <dd>{formatStatusLabel(fileDetail.preview_state)}</dd>
                    </div>
                  </dl>
                </div>

                {libraryPreview?.image_data_url && libraryPreview.scope === "file" ? (
                  <div className="note-card preview-layout-card">
                    <strong>Preview collage</strong>
                    <img className="preview-image" src={libraryPreview.image_data_url} alt="Preview collage" />
                  </div>
                ) : null}

                <div className="note-card">
                  <strong>Assigned tags</strong>
                  {selectedFileTags?.tags?.length ? (
                    <div className="tag-pill-list">
                      {selectedFileTags.tags.map((tag) => (
                        <span key={`${tag.tag_key}-${tag.assigned_at}`} className="tree-badge tree-badge-in_progress">
                          {tag.display_name} {formatConfidence(tag.confidence)}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <p>No tags stored for this video yet.</p>
                  )}
                </div>

                <div className="inline-actions">
                  <button type="button" className="mini-button" onClick={() => openPlaybackOverlay(selectedFile)}>
                    Open playback
                  </button>
                  <button type="button" className="mini-button" onClick={() => openConvertDialog("file")}>
                    Convert file
                  </button>
                  <button type="button" className="mini-button" disabled={isWorking} onClick={handleFilePreviewJob}>
                    Preview file
                  </button>
                  <button type="button" className="mini-button" disabled={isWorking} onClick={handleFileTagJob}>
                    Tag file
                  </button>
                  <button type="button" className="mini-button" onClick={() => openTuneOverlay(selectedFile)}>
                    Tune file
                  </button>
                </div>
              </div>
            ) : (
              <div className="empty-state compact">
                <p>Loading video details...</p>
              </div>
            )}
          </section>
        </div>
      ) : null}

      {activeOverlay === "playback" ? (
        <div className="overlay-backdrop" onClick={() => setActiveOverlay(null)}>
          <section className="overlay panel modal-shell" onClick={(event) => event.stopPropagation()}>
            <div className="panel-header">
              <div>
                <p className="section-kicker">Playback</p>
                <h2>{playbackTarget?.file?.file_name ?? "Loading..."}</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => setActiveOverlay(null)}>
                Close
              </button>
            </div>

            {playbackTarget ? (
              playbackTarget.mode === "embedded" ? (
                <video className="playback-video" controls autoPlay src={playbackTarget.embedded_stream_url}>
                  Embedded playback is not supported in this browser.
                </video>
              ) : (
                <div className="note-card">
                  <strong>External opening</strong>
                  <p>This video opens outside the app according to the configured playback mode.</p>
                  <p className="muted">Path: {playbackTarget.external_path}</p>
                  <p className="muted">Link: {playbackTarget.external_link}</p>
                  <div className="inline-actions">
                    <a className="ghost-button" href={playbackTarget.external_link}>
                      Open link
                    </a>
                  </div>
                </div>
              )
            ) : (
              <div className="empty-state compact">
                <p>Resolving playback target...</p>
              </div>
            )}
          </section>
        </div>
      ) : null}

      {activeOverlay === "logs" ? (
        <div className="overlay-backdrop" onClick={() => setActiveOverlay(null)}>
          <section className="overlay panel modal-shell" onClick={(event) => event.stopPropagation()}>
            <div className="panel-header">
              <div>
                <p className="section-kicker">Log viewer</p>
                <h2>Near-real-time activity</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => setActiveOverlay(null)}>
                Close
              </button>
            </div>

            <div className="form-grid">
              <label>
                <span>Job ID</span>
                <input value={logFilterJobId} onChange={(event) => setLogFilterJobId(event.target.value)} placeholder="All jobs" />
              </label>
              <label>
                <span>File ID</span>
                <input value={logFilterFileId} onChange={(event) => setLogFilterFileId(event.target.value)} placeholder="All files" />
              </label>
              <label>
                <span>Level</span>
                <select value={logFilterLevel} onChange={(event) => setLogFilterLevel(event.target.value)}>
                  <option value="">All levels</option>
                  <option value="debug">Debug</option>
                  <option value="info">Info</option>
                  <option value="warning">Warning</option>
                  <option value="error">Error</option>
                </select>
              </label>
            </div>

            <pre className="log-console log-console-tall">
              {liveLogEvents.length
                ? liveLogEvents
                    .map(
                      (event) =>
                        `${formatDate(event.created_at)}  ${event.level.toUpperCase()}  ${event.event_type}  ${event.message}`
                    )
                    .join("\n")
                : "No events yet for the current filters."}
            </pre>
          </section>
        </div>
      ) : null}

      {activeOverlay === "tune" && tuneDraft ? (
        <div className="overlay-backdrop" onClick={() => setActiveOverlay(null)}>
          <section className="overlay panel modal-shell" onClick={(event) => event.stopPropagation()}>
            <div className="panel-header">
              <div>
                <p className="section-kicker">Tuning</p>
                <h2>{tuneDraft.fileName}</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => setActiveOverlay(null)}>
                Close
              </button>
            </div>

            <div className="note-card">
              <strong>Advanced workflow</strong>
              <p>
                Tuning always writes separate output files and never replaces the source. Provide comma-separated
                sweep values for one or more axes, then compare results below and promote a winner into a saved
                conversion profile.
              </p>
            </div>

            <div className="form-grid">
              <label>
                <span>Dimension sweep (px)</span>
                <input
                  value={tuneDraft.dimensionValues}
                  onChange={(event) => updateTuneDraft("dimensionValues", event.target.value)}
                  placeholder="1000, 900, 800"
                />
              </label>
              <label>
                <span>Quality sweep (CRF)</span>
                <input
                  value={tuneDraft.qualityValues}
                  onChange={(event) => updateTuneDraft("qualityValues", event.target.value)}
                  placeholder="20, 23, 28"
                />
              </label>
              <label>
                <span>Codec sweep</span>
                <input
                  value={tuneDraft.codecValues}
                  onChange={(event) => updateTuneDraft("codecValues", event.target.value)}
                  placeholder="h265, h264"
                />
              </label>
            </div>

            <div className="inline-actions">
              <button type="button" className="primary-button" disabled={isWorking} onClick={submitTuneJob}>
                Start tuning sweep
              </button>
              {tuneJob ? (
                <button type="button" className="ghost-button" onClick={() => refreshTuneJob(tuneJob.id)}>
                  Refresh
                </button>
              ) : null}
            </div>

            {tuneJob ? (
              <div className="job-items-block">
                <h4>
                  Variants · {tuneJob.item_counts.completed}/{tuneJob.item_counts.total} completed
                </h4>
                <div className="job-items-list">
                  {tuneItems.map((item) => (
                    <article key={item.id} className="job-item-row">
                      <div>
                        <strong>{item.variant_params?.label ?? item.item_key}</strong>
                        <p className="row-subtitle">{item.message || "-"}</p>
                      </div>
                      <span className={`state-pill state-${item.status}`}>{item.status}</span>
                      {item.status === "completed" ? (
                        <button type="button" className="mini-button" onClick={() => openPromoteDialog(item)}>
                          Promote
                        </button>
                      ) : null}
                    </article>
                  ))}
                </div>
              </div>
            ) : null}

            {promoteDraft ? (
              <div className="note-card note-card-success">
                <strong>Promote variant to conversion profile</strong>
                <div className="form-grid">
                  <label className="full-width">
                    <span>Profile name</span>
                    <input
                      value={promoteDraft.name}
                      onChange={(event) => setPromoteDraft((current) => ({ ...current, name: event.target.value }))}
                    />
                  </label>
                  <label className="toggle-row">
                    <span>Set as default profile</span>
                    <input
                      type="checkbox"
                      checked={promoteDraft.isDefault}
                      onChange={(event) => setPromoteDraft((current) => ({ ...current, isDefault: event.target.checked }))}
                    />
                  </label>
                </div>
                <div className="inline-actions">
                  <button type="button" className="ghost-button" onClick={() => setPromoteDraft(null)}>
                    Cancel
                  </button>
                  <button type="button" className="primary-button" disabled={isWorking} onClick={submitPromoteTuneVariant}>
                    Save as profile
                  </button>
                </div>
              </div>
            ) : null}
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
                ) : selectedSettingsSection === "tagging" ? (
                  <div className="source-settings">
                    <p>
                      Tagging stays separate from conversion and preview. The backend only stores
                      tags selected from this allowed vocabulary plus confidence scores.
                    </p>
                    <div className="form-grid">
                      <label>
                        <span>Provider</span>
                        <select
                          value={taggingSettings.provider}
                          onChange={(event) => updateTaggingSetting("provider", event.target.value)}
                        >
                          <option value="openrouter">OpenRouter</option>
                          <option value="gemini">Google Gemini</option>
                          <option value="fal">FAL</option>
                          <option value="mistral">Mistral</option>
                        </select>
                      </label>
                      <label>
                        <span>Sample count</span>
                        <input
                          type="number"
                          min="3"
                          max="24"
                          value={taggingSettings.sample_count}
                          onChange={(event) => updateTaggingSetting("sample_count", Number(event.target.value))}
                        />
                      </label>
                      <label className="toggle-row">
                        <span>Combine frames</span>
                        <input
                          type="checkbox"
                          checked={taggingSettings.combine_frames}
                          onChange={(event) => updateTaggingSetting("combine_frames", event.target.checked)}
                        />
                      </label>
                      <label className="toggle-row">
                        <span>Prefer batch</span>
                        <input
                          type="checkbox"
                          checked={taggingSettings.prefer_batch}
                          onChange={(event) => updateTaggingSetting("prefer_batch", event.target.checked)}
                        />
                      </label>
                      <label className="full-width">
                        <span>Allowed vocabulary</span>
                        <textarea
                          rows="10"
                          value={(taggingSettings.vocabulary ?? []).join("\n")}
                          onChange={(event) =>
                            updateTaggingSetting(
                              "vocabulary",
                              event.target.value
                                .split("\n")
                                .map((entry) => entry.trim())
                                .filter(Boolean)
                            )
                          }
                          placeholder="One tag per line"
                        />
                      </label>
                    </div>
                    <div className="inline-actions">
                      <button type="button" className="primary-button" disabled={isWorking} onClick={handleSaveTaggingSettings}>
                        Save tagging settings
                      </button>
                    </div>
                    <div className="note-card">
                      <strong>Closed vocabulary only</strong>
                      <p>
                        The model can only return tags from this list. Any out-of-vocabulary labels
                        are discarded before storage.
                      </p>
                    </div>
                  </div>
                ) : selectedSettingsSection === "providers" ? (
                  <div className="source-settings">
                    <p>
                      Configure backend-only provider access here. API keys stay out of the main
                      metadata database and are stored separately.
                    </p>
                    <div className="provider-settings-list">
                      {providerSettings.map((provider) => (
                        <div key={provider.provider} className="note-card">
                          <div className="panel-header compact-header">
                            <div>
                              <strong>{provider.provider === "gemini" ? "Google Gemini" : provider.provider.toUpperCase()}</strong>
                              <p className="muted">
                                {provider.api_key_configured ? "API key stored" : "API key not stored"}
                              </p>
                            </div>
                            <label className="toggle-row">
                              <span>Enabled</span>
                              <input
                                type="checkbox"
                                checked={provider.enabled}
                                onChange={(event) => updateProviderSetting(provider.provider, "enabled", event.target.checked)}
                              />
                            </label>
                          </div>
                          <div className="form-grid">
                            <label>
                              <span>Vision model</span>
                              <input
                                value={provider.vision_model}
                                onChange={(event) => updateProviderSetting(provider.provider, "vision_model", event.target.value)}
                              />
                            </label>
                            <label>
                              <span>Text model</span>
                              <input
                                value={provider.text_model}
                                onChange={(event) => updateProviderSetting(provider.provider, "text_model", event.target.value)}
                                placeholder="Optional"
                              />
                            </label>
                            <label>
                              <span>API key</span>
                              <input
                                type="password"
                                value={provider.api_key}
                                onChange={(event) => updateProviderSetting(provider.provider, "api_key", event.target.value)}
                                placeholder={provider.api_key_configured ? "Leave blank to keep stored key" : ""}
                              />
                            </label>
                            <label className="toggle-row">
                              <span>Prefer batch</span>
                              <input
                                type="checkbox"
                                checked={provider.prefer_batch}
                                onChange={(event) => updateProviderSetting(provider.provider, "prefer_batch", event.target.checked)}
                              />
                            </label>
                          </div>
                        </div>
                      ))}
                    </div>
                    <div className="inline-actions">
                      <button type="button" className="primary-button" disabled={isWorking} onClick={handleSaveProviderSettings}>
                        Save provider settings
                      </button>
                    </div>
                  </div>
                ) : selectedSettingsSection === "playback" ? (
                  <div className="source-settings">
                    <p>
                      Choose how videos open from the library: play them embedded in-app, or open them externally
                      by path or link when the environment supports it.
                    </p>
                    <div className="form-grid">
                      <label className="full-width">
                        <span>Playback mode</span>
                        <select
                          value={playbackSettings.mode}
                          onChange={(event) => setPlaybackSettings({ ...playbackSettings, mode: event.target.value })}
                        >
                          <option value="embedded">Embedded modal playback</option>
                          <option value="external">External opening by path or link</option>
                        </select>
                      </label>
                    </div>
                    <div className="inline-actions">
                      <button type="button" className="primary-button" disabled={isWorking} onClick={handleSavePlaybackSettings}>
                        Save playback settings
                      </button>
                    </div>
                    <div className="note-card">
                      <strong>Behavior</strong>
                      <p>
                        Embedded mode streams the file through the backend into an in-app player. External mode
                        resolves the file's direct path and a protocol-appropriate link instead of streaming it.
                      </p>
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
