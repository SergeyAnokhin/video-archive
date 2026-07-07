import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
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
  getDirectoryPreviewCardUrl,
  getFilePreviewCardUrl,
  loadAppShellData,
  reconnectSource,
  restartJob,
  saveProviderSettings,
  saveSettings,
  saveSource,
  testSourceConnection,
  updatePreviewLayout
} from "./api";
import AppHeader from "./components/layout/AppHeader";
import FileBrowserPanel from "./components/layout/FileBrowserPanel";
import FileDetailsModal from "./components/modals/FileDetailsModal";
import JobsModal from "./components/modals/JobsModal";
import LogViewerModal from "./components/modals/LogViewerModal";
import PlaybackModal from "./components/modals/PlaybackModal";
import ConversionModal from "./components/modals/ConversionModal";
import PromotionModal from "./components/modals/PromotionModal";
import TuneModal from "./components/modals/TuneModal";
import SettingsModal from "./components/settings/SettingsModal";
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
  isLocalProtocol,
  toSourceForm,
  toSourcePayload,
  toTaggingForm
} from "./features/source/sourceHelpers";
import {
  formatBytes,
  formatConfidence,
  formatDate,
  formatJobScope,
  formatJobTypeLabel,
  formatProfileLabel,
  formatStatusLabel,
  renderIndicatorBadges
} from "./appFormatters";
import { getNextVisualMode, getSettingsSections, visualModes } from "./appShellConfig";
import { createTranslator } from "./i18n";

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
  const [activeOverlay, setActiveOverlay] = useState(null);
  const [conversionDraft, setConversionDraft] = useState(null);
  const [previewSettings, setPreviewSettings] = useState(defaultPreviewSettings);
  const [playbackSettings, setPlaybackSettings] = useState(defaultPlaybackSettings);
  const [taggingSettings, setTaggingSettings] = useState(defaultTaggingSettings);
  const [providerSettings, setProviderSettings] = useState(defaultProviderSettings);
  const [previewPresets, setPreviewPresets] = useState([]);
  const [previewPresetName, setPreviewPresetName] = useState("");
  const [livePreview, setLivePreview] = useState(null);
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
  const [locale, setLocale] = useState(() => window.localStorage.getItem("video-archive.locale") || "ru");
  const [visualMode, setVisualMode] = useState(() => window.localStorage.getItem("video-archive.visual-mode") || "strict");
  const [librarySearchQuery, setLibrarySearchQuery] = useState("");
  const logConsoleRef = useRef(null);
  const t = useMemo(() => createTranslator(locale), [locale]);

  const treeItems = useMemo(() => flattenTree(tree), [tree]);
  const visibleFiles = useMemo(() => files.filter((file) => file.is_video_supported), [files]);
  const deferredLibrarySearchQuery = useDeferredValue(librarySearchQuery);
  const selectedFile = visibleFiles.find((file) => file.id === selectedFileId) ?? visibleFiles[0] ?? null;
  const settingsSections = useMemo(() => getSettingsSections(t), [t]);
  const liveSourceLabel = source?.name ?? info.active_source?.name ?? t("app.noActiveSource");
  const pendingJobsCount = (info.queue.running_jobs ?? 0) + (info.queue.queued_jobs ?? 0);
  const hasActiveQueue = pendingJobsCount > 0;
  const backendLabel =
    health.state === "ready"
      ? t("app.backendReady", { status: health.status })
      : health.state === "loading"
        ? t("app.backendLoading")
        : t("app.backendOffline");
  const sourceFormIsLocal = isLocalProtocol(sourceForm.protocol);
  const formatDateValue = (value) => formatDate(value, locale);
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
    window.localStorage.setItem("video-archive.locale", locale);
    document.documentElement.lang = locale;
  }, [locale]);

  useEffect(() => {
    const currentMode = visualModes.includes(visualMode) ? visualMode : "strict";
    document.documentElement.dataset.visualMode = currentMode;
    window.localStorage.setItem("video-archive.visual-mode", currentMode);
  }, [visualMode]);

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
    if (!visibleFiles.length) {
      if (selectedFileId !== null) {
        setSelectedFileId(null);
      }
      return;
    }

    if (!selectedFileId || !visibleFiles.some((file) => file.id === selectedFileId)) {
      setSelectedFileId(visibleFiles[0].id);
    }
  }, [visibleFiles, selectedFileId]);

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
    let payload;
    try {
      payload = await loadAppShellData();
      setHealth({ state: "ready", status: payload.health.status, error: null });
    } catch (error) {
      setHealth({ state: "error", status: null, error: error.message });
      setActionError(error.message);
      return;
    }

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
      return;
    }

    try {
      const [treePayload, jobsPayload] = await Promise.all([fetchTree(), fetchJobs()]);
      const flatNodes = flattenTree(treePayload.tree);
      const nextDirectory = flatNodes.some((node) => node.path === preferredDirectory) ? preferredDirectory : "";
      const filesPayload = await fetchFiles(nextDirectory);

      setTree(treePayload.tree);
      setJobs(jobsPayload.jobs);
      setFiles(filesPayload.files);
      setSelectedDirectory(nextDirectory);
    } catch (error) {
      setActionError(error.message);
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
        const nextSettings = { ...defaultPreviewSettings, ...(settingsPayload.settings?.preview ?? {}) };
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
    setTestResult(null);
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
        directories: payload.directories ?? [],
        favorites: payload.favorites ?? []
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
    setTestResult(null);
    try {
      const payload = await saveSource(toSourcePayload(sourceForm));
      const savedSource = payload?.source ?? null;
      if (!savedSource) {
        throw new Error("Save source response did not include the active source.");
      }
      setSource(savedSource);
      setSourceForm(toSourceForm(savedSource));
      setActionMessage(t("messages.sourceSaved"));
      setTestResult({
        ok: true,
        protocol: savedSource.protocol,
        host: savedSource.host,
        port: savedSource.port,
        root_path: savedSource.root_path,
        message: t("messages.sourceSaved")
      });
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
      setActionMessage(t("messages.previewSaved"));
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
      setActionMessage(t("messages.playbackSaved"));
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
      setActionMessage(t("messages.taggingSaved"));
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
      setActionMessage(t("messages.providersSaved"));
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
      aspect_ratio_preset: preset.layout_definition?.aspect_ratio_preset ?? previewSettings.aspect_ratio_preset ?? defaultPreviewSettings.aspect_ratio_preset,
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
        aspect_ratio_preset: previewSettings.aspect_ratio_preset,
        layout_definition: { kind: "auto-grid", version: 1, aspect_ratio_preset: previewSettings.aspect_ratio_preset }
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
      setActionMessage(mode === "update" ? t("messages.presetUpdated") : t("messages.presetSaved"));
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
        throw new Error(t("messages.noProfiles"));
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
    setSelectedFileId(file.id);
    try {
      const payload = await fetchPlaybackTarget(file.id);
      if (payload.playback.mode === "external") {
        if (!payload.playback.external_supported || !payload.playback.external_url) {
          throw new Error("External playback is not available for this file path.");
        }
        window.open(payload.playback.external_url, "_blank", "noopener,noreferrer");
        setActionMessage(t("messages.externalPlayback", { name: file.file_name }));
        return;
      }
      setPlaybackTarget(payload.playback);
      setActiveOverlay("playback");
    } catch (error) {
      setActionError(error.message);
    }
  }

  async function openDetailsModal(fileId = selectedFile?.id) {
    if (!fileId) {
      return;
    }
    setActionError(null);
    setSelectedFileId(fileId);
    setSelectedFileDetails(null);
    setSelectedFilePreview(null);
    setSelectedFileLogs([]);
    setActiveOverlay("details");
    await loadSelectedFileContext(fileId);
  }

  function getFilePreviewImageUrl(file) {
    if (!file?.id || !file.has_preview_assets) {
      return "";
    }
    return `/api/files/${encodeURIComponent(file.id)}/preview-image`;
  }

  function getFilePreviewCardImageUrl(file) {
    if (!file?.id || !file.has_preview_assets) {
      return "";
    }
    return getFilePreviewCardUrl(file.id);
  }

  function getDirectoryPreviewCardImageUrl(directory) {
    if (!directory?.has_preview_asset) {
      return "";
    }
    return getDirectoryPreviewCardUrl(directory.path ?? "");
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
      setActionMessage(t("messages.profileSaved", { name: payload.profile.name }));
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
      setActionMessage(t("messages.tuningProfileSaved", { name: payload.profile.name }));
    } catch (error) {
      setActionError(error.message);
    } finally {
      setIsWorking(false);
    }
  }

  return (
    <main className="app-shell">
      <AppHeader
        healthState={health.state}
        backendLabel={backendLabel}
        actionError={actionError}
        actionMessage={actionMessage}
        liveSourceLabel={liveSourceLabel}
        pendingJobsCount={pendingJobsCount}
        hasActiveQueue={hasActiveQueue}
        source={source}
        isWorking={isWorking}
        locale={locale}
        visualMode={visualMode}
        librarySearchQuery={librarySearchQuery}
        t={t}
        onScanSource={handleScanSource}
        onOpenLogs={() => openLogViewer()}
        onOpenJobs={openJobsOverlay}
        onOpenSettings={() => {
          setSelectedSettingsSection("preview");
          setActiveOverlay("settings");
        }}
        onLibrarySearchChange={setLibrarySearchQuery}
        onToggleLocale={() => setLocale((current) => (current === "ru" ? "en" : "ru"))}
        onCycleVisualMode={() => setVisualMode((current) => getNextVisualMode(current))}
      />

      <section className="workspace">
        <FileBrowserPanel
          treeItems={treeItems}
          selectedDirectory={selectedDirectory}
          source={source}
          selectedFile={selectedFile}
          isWorking={isWorking}
          files={visibleFiles}
          searchQuery={deferredLibrarySearchQuery}
          onScanSource={handleScanSource}
          onOpenPlayback={handleOpenPlayback}
          onRunDirectoryAction={(action) => {
            if (action === "convert") {
              openConvertDialog("directory");
              return;
            }
            if (action === "preview") {
              handleDirectoryJob(createPreviewDirectoryJob);
              return;
            }
            if (action === "tag") {
              handleDirectoryJob(createTagDirectoryJob);
              return;
            }
            handleRescanDirectory();
          }}
          onSelectDirectory={handleSelectDirectory}
          onSelectFile={setSelectedFileId}
          onOpenFileDetails={openDetailsModal}
          renderIndicatorBadges={(indicators) => renderIndicatorBadges(indicators, t)}
          getFilePreviewImageUrl={getFilePreviewCardImageUrl}
          getDirectoryPreviewImageUrl={getDirectoryPreviewCardImageUrl}
          formatDirectoryLabel={(path) => formatDirectoryLabel(path, t)}
          formatStatusLabel={(value) => formatStatusLabel(value, t)}
          t={t}
        />
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
        formatDate={formatDateValue}
        formatStatusLabel={(value) => formatStatusLabel(value, t)}
        t={t}
      />

      <PlaybackModal
        isOpen={activeOverlay === "playback"}
        playbackTarget={playbackTarget}
        onClose={() => setActiveOverlay(null)}
        onOpenInfo={() => openDetailsModal(playbackTarget?.file_id)}
        t={t}
      />

      <LogViewerModal
        isOpen={activeOverlay === "logs"}
        onClose={() => setActiveOverlay(null)}
        logFilters={logFilters}
        onChangeLogFilter={(field, value) => setLogFilters((current) => ({ ...current, [field]: value }))}
        onClearFilters={() => setLogFilters(emptyLogFilters)}
        logEvents={logEvents}
        logConsoleRef={logConsoleRef}
        formatDate={formatDateValue}
        t={t}
      />

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
        formatDate={formatDateValue}
        formatStatusLabel={(value) => formatStatusLabel(value, t)}
        formatJobScope={(job) => formatJobScope(job, t)}
        formatJobTypeLabel={(value) => formatJobTypeLabel(value, t)}
        t={t}
      />

      <ConversionModal
        isOpen={activeOverlay === "convert"}
        conversionDraft={conversionDraft}
        conversionProfiles={conversionProfiles}
        formatProfileLabel={(profile) => formatProfileLabel(profile, t)}
        isWorking={isWorking}
        onClose={() => setActiveOverlay(null)}
        onUpdateProfileId={(value) => updateConversionDraft("profileId", value)}
        onUpdateMode={(value) => updateConversionDraft("mode", value)}
        onSubmit={submitConversionJob}
        t={t}
      />

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
        formatDate={formatDateValue}
        t={t}
      />

      <PromotionModal
        isOpen={Boolean(promotionDraft)}
        promotionDraft={promotionDraft}
        isWorking={isWorking}
        onClose={() => setPromotionDraft(null)}
        onUpdate={(field, value) => setPromotionDraft((current) => ({ ...current, [field]: value }))}
        onSubmit={handlePromoteVariant}
        t={t}
      />

      <SettingsModal
        isOpen={activeOverlay === "settings"}
        onClose={() => setActiveOverlay(null)}
        settingsSections={settingsSections}
        selectedSettingsSection={selectedSettingsSection}
        onSelectSection={setSelectedSettingsSection}
        source={source}
        sourceForm={sourceForm}
        sourceFormIsLocal={sourceFormIsLocal}
        isWorking={isWorking}
        localDirectoryBrowser={localDirectoryBrowser}
        isLocalDirectoryBrowserOpen={isLocalDirectoryBrowserOpen}
        testResult={testResult}
        t={t}
        onUpdateSourceField={updateSourceField}
        onLoadLocalDirectoryBrowser={loadLocalDirectoryBrowser}
        onSelectLocalDirectory={handleSelectLocalDirectory}
        onSourceTest={handleSourceTest}
        onReconnect={handleReconnect}
        onScanSource={handleScanSource}
        onSourceSave={handleSourceSave}
        profileDraft={profileDraft}
        onUpdateProfileDraft={updateProfileDraft}
        onCreateProfile={handleCreateProfile}
        conversionProfiles={conversionProfiles}
        formatProfileLabel={(profile) => formatProfileLabel(profile, t)}
        previewSettings={previewSettings}
        onUpdatePreviewSetting={updatePreviewSetting}
        previewPresets={previewPresets}
        previewPresetName={previewPresetName}
        onPreviewPresetNameChange={setPreviewPresetName}
        onLoadPreset={handleLoadPreset}
        onSavePreset={handleSavePreset}
        livePreview={livePreview}
        onSavePreviewSettings={handleSavePreviewSettings}
        playbackSettings={playbackSettings}
        onUpdatePlaybackSetting={updatePlaybackSetting}
        onSavePlaybackSettings={handleSavePlaybackSettings}
        taggingSettings={taggingSettings}
        onUpdateTaggingSetting={updateTaggingSetting}
        onSaveTaggingSettings={handleSaveTaggingSettings}
        providerSettings={providerSettings}
        onUpdateProviderSetting={updateProviderSetting}
        onSaveProviderSettings={handleSaveProviderSettings}
      />
    </main>
  );
}

export default App;
