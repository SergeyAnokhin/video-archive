import { useEffect, useMemo, useRef, useState } from "react";
import {
  cancelJob,
  createConversionProfile,
  createConvertDirectoryJob,
  createConvertFileJob,
  createPreviewDirectoryJob,
  createPreviewFileJob,
  createTagDirectoryJob,
  createTagFileJob,
  createRescanDirectoryJob,
  createScanSourceJob,
  createTuneFileJob,
  createPreviewLayout,
  fallbackInfo,
  fetchConversionProfiles,
  fetchDirectoryPreview,
  fetchFileDetails,
  fetchFilePreview,
  fetchFileTags,
  fetchFiles,
  fetchJobs,
  fetchJob,
  fetchJobItems,
  fetchLocalDirectories,
  fetchLogs,
  fetchPlaybackTarget,
  fetchPreviewLayouts,
  fetchProviderSettings,
  fetchSettings,
  fetchTree,
  generateLivePreview,
  loadAppShellData,
  reconnectSource,
  restartJob,
  saveProviderSettings,
  saveSettings,
  saveSource,
  testSourceConnection,
  updatePreviewLayout
} from "./api";
import FileDetailsModal from "./components/modals/FileDetailsModal";
import JobsModal from "./components/modals/JobsModal";
import TuneModal from "./components/modals/TuneModal";
import {
  buildProfilePayloadFromVariant,
  buildTuneSweep,
  defaultPlaybackSettings,
  defaultPreviewSettings,
  defaultProviderSettings,
  defaultTaggingSettings,
  defaultTuneDraft,
  emptyLocalDirectoryBrowser,
  emptyLogFilters,
  emptyProfileDraft,
  emptySourceForm,
  flattenTree,
  formatDirectoryLabel,
  formatSourceSummary,
  isLocalProtocol,
  toSourceForm,
  toSourcePayload,
  toTaggingForm
} from "./features/source/sourceHelpers";
import SourceSettingsSection from "./features/source/SourceSettingsSection";
import { settingsSections } from "./mockData";

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

function formatProfileLabel(profile) {
  const parts = [`${profile.video_codec.toUpperCase()} -> ${profile.container.toUpperCase()}`];
  if (profile.max_dimension) {
    parts.push(`max ${profile.max_dimension}px`);
  }
  if (profile.quality_value) {
    parts.push(`${(profile.quality_mode || "quality").toUpperCase()} ${profile.quality_value}`);
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
  const [playbackSettings, setPlaybackSettings] = useState(defaultPlaybackSettings);
  const [taggingSettings, setTaggingSettings] = useState(defaultTaggingSettings);
  const [providerSettings, setProviderSettings] = useState(defaultProviderSettings);
  const [previewPresets, setPreviewPresets] = useState([]);
  const [previewPresetName, setPreviewPresetName] = useState("");
  const [livePreview, setLivePreview] = useState(null);
  const [libraryPreview, setLibraryPreview] = useState(null);
  const [selectedFileTags, setSelectedFileTags] = useState(null);
  const [selectedFileDetails, setSelectedFileDetails] = useState(null);
  const [selectedFilePreview, setSelectedFilePreview] = useState(null);
  const [selectedFileLogs, setSelectedFileLogs] = useState([]);
  const [playbackTarget, setPlaybackTarget] = useState(null);
  const [logFilters, setLogFilters] = useState(emptyLogFilters);
  const [logEvents, setLogEvents] = useState([]);
  const [profileDraft, setProfileDraft] = useState(emptyProfileDraft);
  const [tuneDraft, setTuneDraft] = useState(defaultTuneDraft);
  const [tuningJobId, setTuningJobId] = useState(null);
  const [tuningJob, setTuningJob] = useState(null);
  const [tuningItems, setTuningItems] = useState([]);
  const [tuningEvents, setTuningEvents] = useState([]);
  const [promotionDraft, setPromotionDraft] = useState(null);
  const [actionMessage, setActionMessage] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [testResult, setTestResult] = useState(null);
  const [localDirectoryBrowser, setLocalDirectoryBrowser] = useState(emptyLocalDirectoryBrowser);
  const [isLocalDirectoryBrowserOpen, setIsLocalDirectoryBrowserOpen] = useState(false);
  const [isWorking, setIsWorking] = useState(false);
  const logConsoleRef = useRef(null);

  const treeItems = useMemo(() => flattenTree(tree), [tree]);
  const selectedFile = files.find((file) => file.id === selectedFileId) ?? files[0] ?? null;
  const liveSourceLabel = source?.name ?? info.active_source?.name ?? "No active source";
  const liveSourceMeta = formatSourceSummary(source);
  const queueSummary = `${info.queue.running_jobs} running - ${info.queue.queued_jobs} queued`;
  const backendLabel =
    health.state === "ready"
      ? `Backend ${health.status}`
      : health.state === "loading"
        ? "Connecting backend"
        : "Backend offline";
  const sourceFormIsLocal = isLocalProtocol(sourceForm.protocol);
  const tuningVariants = useMemo(() => {
    const variantsById = new Map((tuningJob?.parameters?.variants ?? []).map((variant) => [variant.id, variant]));
    return tuningItems.map((item) => ({
      item,
      variant: variantsById.get(item.item_key) ?? null
    }));
  }, [tuningItems, tuningJob]);

  useEffect(() => {
    loadBootstrap();
  }, []);

  useEffect(() => {
    if (!sourceFormIsLocal) {
      setIsLocalDirectoryBrowserOpen(false);
      setLocalDirectoryBrowser(emptyLocalDirectoryBrowser);
    }
  }, [sourceFormIsLocal]);

  useEffect(() => {
    setTestResult(null);
  }, [sourceForm.protocol]);

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
          return [...current, payload].slice(-300);
        });
      } catch {
        return;
      }
    };
    return () => eventSource.close();
  }, [activeOverlay, selectedJobId]);

  useEffect(() => {
    if (activeOverlay !== "logs") {
      return undefined;
    }

    loadLogViewer();
    const params = new URLSearchParams();
    if (logFilters.jobId) {
      params.set("job_id", logFilters.jobId);
    }
    if (logFilters.fileId) {
      params.set("file_id", logFilters.fileId);
    }
    if (logFilters.level) {
      params.set("level", logFilters.level);
    }
    const eventSource = new EventSource(`/api/logs/stream${params.toString() ? `?${params}` : ""}`);
    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        setLogEvents((current) => {
          if (current.some((entry) => entry.stream_id === payload.stream_id)) {
            return current;
          }
          return [...current, payload].slice(-400);
        });
      } catch {
        return;
      }
    };
    return () => eventSource.close();
  }, [activeOverlay, logFilters.jobId, logFilters.fileId, logFilters.level]);

  useEffect(() => {
    if (!logConsoleRef.current || activeOverlay !== "logs") {
      return;
    }
    logConsoleRef.current.scrollTop = logConsoleRef.current.scrollHeight;
  }, [logEvents, activeOverlay]);

  useEffect(() => {
    if (activeOverlay !== "settings" || !["preview", "playback", "tagging", "providers", "profiles"].includes(selectedSettingsSection)) {
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

  useEffect(() => {
    if (activeOverlay !== "details" || !selectedFile?.id) {
      return;
    }
    loadSelectedFileContext(selectedFile.id);
  }, [activeOverlay, selectedFile?.id]);

  useEffect(() => {
    if (activeOverlay !== "tune" || !tuningJobId) {
      return undefined;
    }

    refreshTuningJob(tuningJobId);
    const intervalId = window.setInterval(() => {
      refreshTuningJob(tuningJobId);
    }, 3000);
    return () => window.clearInterval(intervalId);
  }, [activeOverlay, tuningJobId]);

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

  async function loadLogViewer() {
    try {
      const payload = await fetchLogs({
        jobId: logFilters.jobId || undefined,
        fileId: logFilters.fileId || undefined,
        level: logFilters.level || undefined,
        limit: 250
      });
      setLogEvents(payload.events);
    } catch (error) {
      setActionError(error.message);
    }
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

      if (section === "playback") {
        const settingsPayload = await fetchSettings();
        setPlaybackSettings({ ...defaultPlaybackSettings, ...(settingsPayload.settings?.playback ?? {}) });
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

      if (section === "profiles") {
        await ensureConversionProfiles(true);
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
        const payload = await fetchFilePreview(fileId);
        if (payload.preview) {
          setLibraryPreview({ ...payload.preview, scope: "file" });
          return;
        }
      }

      const payload = await fetchDirectoryPreview(directoryPath);
      setLibraryPreview(payload.preview ? { ...payload.preview, scope: "directory" } : null);
    } catch (error) {
      setActionError(error.message);
    }
  }

  async function loadSelectedFileTags(fileId) {
    try {
      const payload = await fetchFileTags(fileId);
      setSelectedFileTags(payload);
    } catch (error) {
      setSelectedFileTags(null);
      setActionError(error.message);
    }
  }

  async function loadSelectedFileContext(fileId) {
    try {
      const [detailsPayload, previewPayload, tagsPayload, logsPayload] = await Promise.all([
        fetchFileDetails(fileId),
        fetchFilePreview(fileId),
        fetchFileTags(fileId),
        fetchLogs({ fileId, limit: 150 })
      ]);
      setSelectedFileDetails(detailsPayload.file);
      setSelectedFilePreview(previewPayload.preview ?? null);
      setSelectedFileTags(tagsPayload);
      setSelectedFileLogs(logsPayload.events);
    } catch (error) {
      setActionError(error.message);
    }
  }

  async function refreshTuningJob(jobId) {
    try {
      const [jobPayload, itemsPayload, eventsPayload] = await Promise.all([
        fetchJob(jobId),
        fetchJobItems(jobId),
        fetchLogs({ jobId, limit: 200 })
      ]);
      setTuningJob(jobPayload.job);
      setTuningItems(itemsPayload.items);
      setTuningEvents(eventsPayload.events);
    } catch (error) {
      setActionError(error.message);
    }
  }

  function updateSourceField(field, value) {
    setSourceForm((current) => {
      const next = { ...current, [field]: value };
      if (field === "protocol" && value === "local") {
        next.host = "";
        next.port = "";
        next.username = "";
        next.password = "";
      }
      return next;
    });
  }

  async function loadLocalDirectoryBrowser(path = "") {
    setIsWorking(true);
    setActionError(null);
    try {
      const payload = await fetchLocalDirectories(path);
      setLocalDirectoryBrowser({
        path: payload.path ?? "",
        parent_path: payload.parent_path ?? null,
        directories: payload.directories ?? []
      });
      setIsLocalDirectoryBrowserOpen(true);
    } catch (error) {
      setActionError(error.message);
    } finally {
      setIsWorking(false);
    }
  }

  function handleSelectLocalDirectory(path) {
    updateSourceField("root_path", path);
    if (!sourceForm.name.trim()) {
      const segments = path.split(/[/\\]+/).filter(Boolean);
      const leaf = segments[segments.length - 1] ?? path;
      updateSourceField("name", `Local ${leaf}`);
    }
  }

  function updatePreviewSetting(field, value) {
    setPreviewSettings((current) => ({ ...current, [field]: value }));
  }

  function updatePlaybackSetting(field, value) {
    setPlaybackSettings((current) => ({ ...current, [field]: value }));
  }

  function updateTaggingSetting(field, value) {
    setTaggingSettings((current) => ({ ...current, [field]: value }));
  }

  function updateProviderSetting(providerName, field, value) {
    setProviderSettings((current) =>
      current.map((entry) => (entry.provider === providerName ? { ...entry, [field]: value } : entry))
    );
  }

  function updateProfileDraft(field, value) {
    setProfileDraft((current) => ({ ...current, [field]: value }));
  }

  function updateTuneDraft(field, value) {
    setTuneDraft((current) => ({ ...current, [field]: value }));
  }

  function updateTuneCodec(codec, enabled) {
    setTuneDraft((current) => ({ ...current, codecs: { ...current.codecs, [codec]: enabled } }));
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

  async function handleFilePreviewJob(fileId = selectedFile?.id) {
    if (!fileId) {
      return;
    }

    setIsWorking(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const payload = await createPreviewFileJob(fileId);
      setActionMessage(payload.job.summary_message);
      await refreshLibrary(selectedDirectory);
      await loadLibraryPreview(fileId, selectedDirectory);
      if (activeOverlay === "details") {
        await loadSelectedFileContext(fileId);
      }
      if (activeOverlay === "jobs") {
        await refreshJobsOverlay(payload.job.id);
      }
    } catch (error) {
      setActionError(error.message);
    } finally {
      setIsWorking(false);
    }
  }

  async function handleFileTagJob(fileId = selectedFile?.id) {
    if (!fileId) {
      return;
    }

    setIsWorking(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const payload = await createTagFileJob(fileId);
      setActionMessage(payload.job.summary_message);
      if (activeOverlay === "details") {
        await loadSelectedFileContext(fileId);
      }
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

  async function handleSavePlaybackSettings() {
    setIsWorking(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const payload = await saveSettings({ playback: playbackSettings });
      setPlaybackSettings(payload.settings.playback);
      setActionMessage("Playback settings saved.");
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

  async function ensureConversionProfiles(force = false) {
    if (conversionProfiles.length && !force) {
      return conversionProfiles;
    }
    const payload = await fetchConversionProfiles();
    setConversionProfiles(payload.profiles);
    return payload.profiles;
  }

  async function openConvertDialog(scope, fileOverride = selectedFile) {
    setActionError(null);
    try {
      const profiles = await ensureConversionProfiles();
      const defaultProfile = profiles.find((profile) => profile.is_default) ?? profiles[0] ?? null;
      if (!defaultProfile) {
        throw new Error("No saved conversion profiles are available.");
      }

      setConversionDraft({
        scope,
        fileId: scope === "file" ? fileOverride?.id ?? null : null,
        relativePath: selectedDirectory,
        fileName: scope === "file" ? fileOverride?.file_name ?? "" : "",
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

  async function handleOpenPlayback(file = selectedFile) {
    if (!file?.id) {
      return;
    }
    setActionError(null);
    try {
      const payload = await fetchPlaybackTarget(file.id);
      if (payload.playback.mode === "external") {
        if (!payload.playback.external_supported || !payload.playback.external_url) {
          throw new Error("External playback is not available for this file path.");
        }
        window.open(payload.playback.external_url, "_blank", "noopener,noreferrer");
        setActionMessage(`Requested external playback for ${file.file_name}.`);
        return;
      }
      setPlaybackTarget(payload.playback);
      setActiveOverlay("playback");
    } catch (error) {
      setActionError(error.message);
    }
  }

  async function openDetailsModal() {
    if (!selectedFile?.id) {
      return;
    }
    setActionError(null);
    setSelectedFileDetails(null);
    setSelectedFilePreview(null);
    setSelectedFileLogs([]);
    setActiveOverlay("details");
    await loadSelectedFileContext(selectedFile.id);
  }

  function openTuneModal() {
    setTuneDraft(defaultTuneDraft);
    setTuningJobId(null);
    setTuningJob(null);
    setTuningItems([]);
    setTuningEvents([]);
    setActiveOverlay("tune");
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

  function openLogViewer(preset = emptyLogFilters) {
    setLogFilters(preset);
    setLogEvents([]);
    setActiveOverlay("logs");
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

  async function handleCreateProfile() {
    setIsWorking(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const payload = await createConversionProfile({
        ...profileDraft,
        max_dimension: profileDraft.max_dimension === "" ? null : Number(profileDraft.max_dimension),
        quality_mode: profileDraft.quality_value ? profileDraft.quality_mode : null,
        quality_value: profileDraft.quality_value || null,
        extra_encoder_args: profileDraft.extra_encoder_args || null
      });
      setProfileDraft(emptyProfileDraft);
      await ensureConversionProfiles(true);
      setActionMessage(`Saved conversion profile ${payload.profile.name}.`);
    } catch (error) {
      setActionError(error.message);
    } finally {
      setIsWorking(false);
    }
  }

  async function handleRunTune() {
    if (!selectedFile?.id) {
      return;
    }
    setIsWorking(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const sweep = buildTuneSweep(tuneDraft);
      const payload = await createTuneFileJob(selectedFile.id, sweep);
      setTuningJobId(payload.job.id);
      setTuningJob(payload.job);
      setPromotionDraft(null);
      setActionMessage(payload.job.summary_message);
      await refreshTuningJob(payload.job.id);
    } catch (error) {
      setActionError(error.message);
    } finally {
      setIsWorking(false);
    }
  }

  async function handlePromoteVariant() {
    if (!promotionDraft?.variant) {
      return;
    }
    setIsWorking(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const payload = await createConversionProfile(
        buildProfilePayloadFromVariant(promotionDraft.name.trim(), promotionDraft.variant, promotionDraft.isDefault)
      );
      await ensureConversionProfiles(true);
      setPromotionDraft(null);
      setActionMessage(`Saved profile ${payload.profile.name} from tuning result.`);
    } catch (error) {
      setActionError(error.message);
    } finally {
      setIsWorking(false);
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
            Browse one active source, keep the main library light, and move playback, tuning, logs,
            and deeper file actions into dedicated modal flows.
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
            <button type="button" className="ghost-button" onClick={() => setPreviewVisible((value) => !value)}>
              {previewVisible ? "Hide preview" : "Show preview"}
            </button>
            <button type="button" className="ghost-button" disabled={!source || isWorking} onClick={handleScanSource}>
              Scan source
            </button>
            <button type="button" className="ghost-button" onClick={() => openLogViewer()}>
              Logs
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
            <button type="button" className="mini-button" disabled={!source || isWorking} onClick={handleScanSource}>
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

        <section className="panel file-panel">
          <div className="panel-header">
            <div>
              <p className="section-kicker">Current folder</p>
              <h2>{formatDirectoryLabel(selectedDirectory)}</h2>
              <p className="muted">Primary toolbar stays focused on subtree work and lightweight file entry points.</p>
            </div>
            <div className="inline-actions">
              <button type="button" className="mini-button" disabled={!source || !selectedFile || isWorking} onClick={openDetailsModal}>
                Details
              </button>
              <button type="button" className="mini-button" disabled={!source || !selectedFile || isWorking} onClick={() => handleOpenPlayback()}>
                Open playback
              </button>
              <button type="button" className="mini-button" disabled={!source || isWorking} onClick={() => openConvertDialog("directory")}>
                Convert subtree
              </button>
              <button type="button" className="mini-button" disabled={!source || isWorking} onClick={() => handleDirectoryJob(createPreviewDirectoryJob)}>
                Preview subtree
              </button>
              <button type="button" className="mini-button" disabled={!source || isWorking} onClick={() => handleDirectoryJob(createTagDirectoryJob)}>
                Tag subtree
              </button>
              <button type="button" className="mini-button" disabled={!source || isWorking} onClick={handleRescanDirectory}>
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
                  onDoubleClick={openDetailsModal}
                >
                  <div>
                    <strong>{file.file_name}</strong>
                    <p className="row-subtitle">{file.relative_path}</p>
                  </div>
                  <span>{file.extension || "-"}</span>
                  <span>{formatBytes(file.size_bytes)}</span>
                  <span>{formatDate(file.modified_at)}</span>
                  <div className="state-stack">
                    <span className={`state-pill state-${file.conversion_state}`}>Convert {formatStatusLabel(file.conversion_state)}</span>
                    <span className={`state-pill state-${file.preview_state}`}>Preview {formatStatusLabel(file.preview_state)}</span>
                  </div>
                </article>
              ))
            ) : (
              <div className="empty-state">
                <h3>No files in this folder</h3>
                <p>This folder either has no files yet or has not been discovered by a completed scan.</p>
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
                  <img className="preview-image" src={libraryPreview.image_data_url} alt="Generated preview collage" />
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
                    : "Preview generation is on-demand and remains separate from conversion and tagging."}
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
                <dt>Playback mode</dt>
                <dd>{playbackSettings.mode}</dd>
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
                    {selectedFileTags.tagging_model_info?.provider ?? "-"} - {selectedFileTags.tagging_model_info?.model ?? "-"} -{" "}
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

      <FileDetailsModal
        isOpen={activeOverlay === "details"}
        selectedFile={selectedFile}
        selectedFileDetails={selectedFileDetails}
        selectedFilePreview={selectedFilePreview}
        selectedFileTags={selectedFileTags}
        selectedFileLogs={selectedFileLogs}
        isWorking={isWorking}
        onClose={() => setActiveOverlay(null)}
        onOpenPlayback={handleOpenPlayback}
        onOpenConvertDialog={openConvertDialog}
        onPreviewFile={handleFilePreviewJob}
        onTagFile={handleFileTagJob}
        onOpenTune={openTuneModal}
        onOpenLogViewer={openLogViewer}
        formatBytes={formatBytes}
        formatConfidence={formatConfidence}
        formatDate={formatDate}
        formatStatusLabel={formatStatusLabel}
      />

      {activeOverlay === "playback" && playbackTarget ? (
        <div className="overlay-backdrop" onClick={() => setActiveOverlay(null)}>
          <section className="overlay panel modal-shell playback-shell" onClick={(event) => event.stopPropagation()}>
            <div className="panel-header">
              <div>
                <p className="section-kicker">Playback</p>
                <h2>{playbackTarget.file_name}</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => setActiveOverlay(null)}>
                Close
              </button>
            </div>
            <div className="video-player-shell">
              <video controls className="video-player" src={playbackTarget.embedded_url} />
            </div>
            <div className="note-card">
              <strong>Playback target</strong>
              <p className="break-value">{playbackTarget.path}</p>
            </div>
          </section>
        </div>
      ) : null}

      {activeOverlay === "logs" ? (
        <div className="overlay-backdrop" onClick={() => setActiveOverlay(null)}>
          <section className="overlay panel modal-shell logs-shell" onClick={(event) => event.stopPropagation()}>
            <div className="panel-header">
              <div>
                <p className="section-kicker">Log viewer</p>
                <h2>Near-real-time backend activity</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => setActiveOverlay(null)}>
                Close
              </button>
            </div>
            <div className="log-filter-grid">
              <label>
                <span>Job id</span>
                <input value={logFilters.jobId} onChange={(event) => setLogFilters((current) => ({ ...current, jobId: event.target.value }))} />
              </label>
              <label>
                <span>File id</span>
                <input value={logFilters.fileId} onChange={(event) => setLogFilters((current) => ({ ...current, fileId: event.target.value }))} />
              </label>
              <label>
                <span>Level</span>
                <select value={logFilters.level} onChange={(event) => setLogFilters((current) => ({ ...current, level: event.target.value }))}>
                  <option value="">All levels</option>
                  <option value="debug">Debug</option>
                  <option value="info">Info</option>
                  <option value="warning">Warning</option>
                  <option value="error">Error</option>
                </select>
              </label>
              <div className="inline-actions align-end">
                <button type="button" className="ghost-button" onClick={() => setLogFilters(emptyLogFilters)}>
                  Clear filters
                </button>
              </div>
            </div>
            <pre ref={logConsoleRef} className="log-console tall-console">
              {logEvents.length
                ? logEvents.map((event) => `${formatDate(event.created_at)}  ${event.level.toUpperCase()}  ${event.message}`).join("\n")
                : "No events match the current filters."}
            </pre>
          </section>
        </div>
      ) : null}

      <JobsModal
        isOpen={activeOverlay === "jobs"}
        jobs={jobs}
        selectedJobId={selectedJobId}
        selectedJob={selectedJob}
        jobItems={jobItems}
        jobEvents={jobEvents}
        onClose={() => setActiveOverlay(null)}
        onSelectJob={refreshJobsOverlay}
        onRefreshJob={refreshJobsOverlay}
        onCancelJob={handleCancelJob}
        onRestartJob={handleRestartJob}
        onOpenLogViewer={openLogViewer}
        formatDate={formatDate}
        formatJobScope={formatJobScope}
        formatJobTypeLabel={formatJobTypeLabel}
      />

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
                  Production mode writes a temp file, validates it quickly, and replaces the source
                  only on success. Test mode writes a separate output and preserves the source file.
                </p>
              </div>

              <div className="form-grid">
                <label className="full-width">
                  <span>Saved profile</span>
                  <select value={conversionDraft.profileId} onChange={(event) => updateConversionDraft("profileId", event.target.value)}>
                    {conversionProfiles.map((profile) => (
                      <option key={profile.id} value={profile.id}>
                        {formatProfileLabel(profile)}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  <span>Mode</span>
                  <select value={conversionDraft.mode} onChange={(event) => updateConversionDraft("mode", event.target.value)}>
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

      <TuneModal
        isOpen={activeOverlay === "tune"}
        selectedFile={selectedFile}
        tuneDraft={tuneDraft}
        tuningJob={tuningJob}
        tuningVariants={tuningVariants}
        tuningEvents={tuningEvents}
        isWorking={isWorking}
        onClose={() => setActiveOverlay("details")}
        onUpdateTuneDraft={updateTuneDraft}
        onUpdateTuneCodec={updateTuneCodec}
        onRunTune={handleRunTune}
        onPromoteVariant={(variant) =>
          setPromotionDraft({
            variant,
            name: `Tuned ${variant?.label ?? "Profile"}`,
            isDefault: false
          })
        }
        formatDate={formatDate}
      />

      {promotionDraft ? (
        <div className="overlay-backdrop" onClick={() => setPromotionDraft(null)}>
          <section className="overlay panel modal-shell promote-shell" onClick={(event) => event.stopPropagation()}>
            <div className="panel-header">
              <div>
                <p className="section-kicker">Promote result</p>
                <h2>Save tuning output as profile</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => setPromotionDraft(null)}>
                Close
              </button>
            </div>
            <div className="form-grid">
              <label className="full-width">
                <span>Profile name</span>
                <input value={promotionDraft.name} onChange={(event) => setPromotionDraft((current) => ({ ...current, name: event.target.value }))} />
              </label>
              <label className="toggle-row">
                <span>Mark default</span>
                <input type="checkbox" checked={promotionDraft.isDefault} onChange={(event) => setPromotionDraft((current) => ({ ...current, isDefault: event.target.checked }))} />
              </label>
            </div>
            <div className="note-card">
              <strong>{promotionDraft.variant.label}</strong>
              <p>
                Codec {promotionDraft.variant.video_codec.toUpperCase()} - Max dimension {promotionDraft.variant.max_dimension ?? "source"} -{" "}
                {promotionDraft.variant.quality_value ? `CRF ${promotionDraft.variant.quality_value}` : "default quality"}
              </p>
            </div>
            <div className="inline-actions">
              <button type="button" className="primary-button" disabled={isWorking || !promotionDraft.name.trim()} onClick={handlePromoteVariant}>
                Save profile
              </button>
            </div>
          </section>
        </div>
      ) : null}

      {activeOverlay === "settings" ? (
        <div className="overlay-backdrop" onClick={() => setActiveOverlay(null)}>
          <section className="overlay panel modal-shell settings-shell" onClick={(event) => event.stopPropagation()}>
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
                  <button key={section.id} type="button" className={`settings-link ${selectedSettingsSection === section.id ? "active" : ""}`} onClick={() => setSelectedSettingsSection(section.id)}>
                    {section.label}
                  </button>
                ))}
              </nav>
              <section className="settings-detail">
                <h3>{settingsSections.find((section) => section.id === selectedSettingsSection)?.label}</h3>
                {selectedSettingsSection === "source" ? (
                  <SourceSettingsSection
                    source={source}
                    sourceForm={sourceForm}
                    sourceFormIsLocal={sourceFormIsLocal}
                    isWorking={isWorking}
                    localDirectoryBrowser={localDirectoryBrowser}
                    isLocalDirectoryBrowserOpen={isLocalDirectoryBrowserOpen}
                    testResult={testResult}
                    onUpdateSourceField={updateSourceField}
                    onLoadLocalDirectoryBrowser={loadLocalDirectoryBrowser}
                    onSelectLocalDirectory={handleSelectLocalDirectory}
                    onSourceTest={handleSourceTest}
                    onReconnect={handleReconnect}
                    onScanSource={handleScanSource}
                    onSourceSave={handleSourceSave}
                  />
                ) : selectedSettingsSection === "profiles" ? (
                  <div className="source-settings">
                    <p>Profiles stay reusable and separate from tuning runs. Tuning can promote a winning output here later.</p>
                    <div className="profiles-grid">
                      <div className="note-card">
                        <strong>Create profile</strong>
                        <div className="form-grid">
                          <label>
                            <span>Name</span>
                            <input value={profileDraft.name} onChange={(event) => updateProfileDraft("name", event.target.value)} />
                          </label>
                          <label>
                            <span>Codec</span>
                            <select value={profileDraft.video_codec} onChange={(event) => updateProfileDraft("video_codec", event.target.value)}>
                              <option value="h264">H.264</option>
                              <option value="h265">H.265</option>
                              <option value="av1">AV1</option>
                            </select>
                          </label>
                          <label>
                            <span>Max dimension</span>
                            <input value={profileDraft.max_dimension} onChange={(event) => updateProfileDraft("max_dimension", event.target.value)} placeholder="Optional" />
                          </label>
                          <label>
                            <span>Quality value</span>
                            <input value={profileDraft.quality_value} onChange={(event) => updateProfileDraft("quality_value", event.target.value)} placeholder="20" />
                          </label>
                          <label className="toggle-row">
                            <span>Drop audio</span>
                            <input type="checkbox" checked={profileDraft.drop_audio} onChange={(event) => updateProfileDraft("drop_audio", event.target.checked)} />
                          </label>
                          <label className="toggle-row">
                            <span>Default profile</span>
                            <input type="checkbox" checked={profileDraft.is_default} onChange={(event) => updateProfileDraft("is_default", event.target.checked)} />
                          </label>
                          <label className="full-width">
                            <span>Advanced encoder args</span>
                            <input value={profileDraft.extra_encoder_args} onChange={(event) => updateProfileDraft("extra_encoder_args", event.target.value)} placeholder="Optional ffmpeg encoder args" />
                          </label>
                        </div>
                        <div className="inline-actions">
                          <button type="button" className="primary-button" disabled={isWorking || !profileDraft.name.trim()} onClick={handleCreateProfile}>
                            Save profile
                          </button>
                        </div>
                      </div>

                      <div className="note-card">
                        <strong>Saved profiles</strong>
                        <div className="profile-list">
                          {conversionProfiles.map((profile) => (
                            <article key={profile.id} className="profile-row">
                              <div>
                                <strong>{profile.name}</strong>
                                <p className="row-subtitle">{formatProfileLabel(profile)}</p>
                              </div>
                              {profile.is_default ? <span className="tree-badge">default</span> : null}
                            </article>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                ) : selectedSettingsSection === "preview" ? (
                  <div className="source-settings">
                    <p>Preview generation stays independent from conversion. Save the sampling and large-tile rules here, then use the live preview to inspect the layout before launching jobs.</p>
                    <div className="form-grid">
                      <label>
                        <span>Sample count</span>
                        <input type="number" min="3" max="24" value={previewSettings.sample_count} onChange={(event) => updatePreviewSetting("sample_count", Number(event.target.value))} />
                      </label>
                      <label>
                        <span>Large tile count</span>
                        <input type="number" min="0" max="6" value={previewSettings.large_tile_count} onChange={(event) => updatePreviewSetting("large_tile_count", Number(event.target.value))} />
                      </label>
                      <label>
                        <span>Timeline flow</span>
                        <select value={previewSettings.timeline_flow} onChange={(event) => updatePreviewSetting("timeline_flow", event.target.value)}>
                          <option value="row">Row by row</option>
                          <option value="column">Column by column</option>
                          <option value="shuffle">Shuffled time order</option>
                        </select>
                      </label>
                      <label className="toggle-row">
                        <span>Identity diversity</span>
                        <input type="checkbox" checked={previewSettings.identity_diversity_enabled} onChange={(event) => updatePreviewSetting("identity_diversity_enabled", event.target.checked)} />
                      </label>
                      <label className="full-width">
                        <span>Saved preset</span>
                        <select value={previewSettings.layout_preset_id} onChange={(event) => updatePreviewSetting("layout_preset_id", event.target.value)}>
                          {previewPresets.map((preset) => (
                            <option key={preset.id} value={preset.id}>
                              {preset.name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="full-width">
                        <span>Preset name</span>
                        <input value={previewPresetName} onChange={(event) => setPreviewPresetName(event.target.value)} placeholder="Balanced Grid" />
                      </label>
                    </div>
                    <div className="inline-actions">
                      <button type="button" className="ghost-button" disabled={isWorking} onClick={handleLoadPreset}>
                        Load preset
                      </button>
                      <button type="button" className="ghost-button" disabled={isWorking} onClick={() => handleSavePreset("create")}>
                        Save as new preset
                      </button>
                      <button type="button" className="ghost-button" disabled={isWorking || previewSettings.layout_preset_id === "default-preview-grid"} onClick={() => handleSavePreset("update")}>
                        Update preset
                      </button>
                      <button type="button" className="primary-button" disabled={isWorking} onClick={handleSavePreviewSettings}>
                        Save preview settings
                      </button>
                    </div>
                    <div className="preview-settings-grid">
                      <div className="note-card">
                        <strong>Selection rules</strong>
                        <p>First two large tiles prefer faces. Remaining large tiles prefer figures. When identity diversity is enabled, the backend falls back to separate timeline regions if a full identity pass is too expensive.</p>
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
                ) : selectedSettingsSection === "playback" ? (
                  <div className="source-settings">
                    <p>Playback mode is configurable because embedded viewing and external opening behave differently across machines and browser environments.</p>
                    <div className="form-grid">
                      <label>
                        <span>Playback mode</span>
                        <select value={playbackSettings.mode} onChange={(event) => updatePlaybackSetting("mode", event.target.value)}>
                          <option value="embedded">Embedded modal playback</option>
                          <option value="external">External open</option>
                        </select>
                      </label>
                      <label>
                        <span>External strategy</span>
                        <select value={playbackSettings.external_strategy} onChange={(event) => updatePlaybackSetting("external_strategy", event.target.value)}>
                          <option value="file_uri">File URI / link</option>
                          <option value="path">Path-first</option>
                        </select>
                      </label>
                    </div>
                    <div className="inline-actions">
                      <button type="button" className="primary-button" disabled={isWorking} onClick={handleSavePlaybackSettings}>
                        Save playback settings
                      </button>
                    </div>
                    <div className="note-card">
                      <strong>Current behavior</strong>
                      <p>Embedded playback streams through the backend. External playback opens the resolved file URI when the local environment supports it.</p>
                    </div>
                  </div>
                ) : selectedSettingsSection === "tagging" ? (
                  <div className="source-settings">
                    <p>Tagging stays separate from conversion and preview. The backend only stores tags selected from this allowed vocabulary plus confidence scores.</p>
                    <div className="form-grid">
                      <label>
                        <span>Provider</span>
                        <select value={taggingSettings.provider} onChange={(event) => updateTaggingSetting("provider", event.target.value)}>
                          <option value="openrouter">OpenRouter</option>
                          <option value="gemini">Google Gemini</option>
                          <option value="fal">FAL</option>
                          <option value="mistral">Mistral</option>
                        </select>
                      </label>
                      <label>
                        <span>Sample count</span>
                        <input type="number" min="3" max="24" value={taggingSettings.sample_count} onChange={(event) => updateTaggingSetting("sample_count", Number(event.target.value))} />
                      </label>
                      <label className="toggle-row">
                        <span>Combine frames</span>
                        <input type="checkbox" checked={taggingSettings.combine_frames} onChange={(event) => updateTaggingSetting("combine_frames", event.target.checked)} />
                      </label>
                      <label className="toggle-row">
                        <span>Prefer batch</span>
                        <input type="checkbox" checked={taggingSettings.prefer_batch} onChange={(event) => updateTaggingSetting("prefer_batch", event.target.checked)} />
                      </label>
                      <label className="full-width">
                        <span>Allowed vocabulary</span>
                        <textarea rows="10" value={(taggingSettings.vocabulary ?? []).join("\n")} onChange={(event) => updateTaggingSetting("vocabulary", event.target.value.split("\n").map((entry) => entry.trim()).filter(Boolean))} placeholder="One tag per line" />
                      </label>
                    </div>
                    <div className="inline-actions">
                      <button type="button" className="primary-button" disabled={isWorking} onClick={handleSaveTaggingSettings}>
                        Save tagging settings
                      </button>
                    </div>
                    <div className="note-card">
                      <strong>Closed vocabulary only</strong>
                      <p>The model can only return tags from this list. Any out-of-vocabulary labels are discarded before storage.</p>
                    </div>
                  </div>
                ) : selectedSettingsSection === "providers" ? (
                  <div className="source-settings">
                    <p>Configure backend-only provider access here. API keys stay out of the main metadata database and are stored separately.</p>
                    <div className="provider-settings-list">
                      {providerSettings.map((provider) => (
                        <div key={provider.provider} className="note-card">
                          <div className="panel-header compact-header">
                            <div>
                              <strong>{provider.provider === "gemini" ? "Google Gemini" : provider.provider.toUpperCase()}</strong>
                              <p className="muted">{provider.api_key_configured ? "API key stored" : "API key not stored"}</p>
                            </div>
                            <label className="toggle-row">
                              <span>Enabled</span>
                              <input type="checkbox" checked={provider.enabled} onChange={(event) => updateProviderSetting(provider.provider, "enabled", event.target.checked)} />
                            </label>
                          </div>
                          <div className="form-grid">
                            <label>
                              <span>Vision model</span>
                              <input value={provider.vision_model} onChange={(event) => updateProviderSetting(provider.provider, "vision_model", event.target.value)} />
                            </label>
                            <label>
                              <span>Text model</span>
                              <input value={provider.text_model} onChange={(event) => updateProviderSetting(provider.provider, "text_model", event.target.value)} placeholder="Optional" />
                            </label>
                            <label>
                              <span>API key</span>
                              <input type="password" value={provider.api_key} onChange={(event) => updateProviderSetting(provider.provider, "api_key", event.target.value)} placeholder={provider.api_key_configured ? "Leave blank to keep stored key" : ""} />
                            </label>
                            <label className="toggle-row">
                              <span>Prefer batch</span>
                              <input type="checkbox" checked={provider.prefer_batch} onChange={(event) => updateProviderSetting(provider.provider, "prefer_batch", event.target.checked)} />
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
                ) : (
                  <div className="settings-placeholder">
                    <span>This section remains a secondary maintenance flow and stays out of the main library view.</span>
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
