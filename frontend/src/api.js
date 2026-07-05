const fallbackInfo = {
  version: "0.1.0",
  active_source: null,
  database: {
    status: "not_configured",
    schema_version: null
  },
  queue: {
    status: "idle",
    queued_jobs: 0,
    running_jobs: 0
  }
};

async function readJsonOrThrow(response, label) {
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload?.error?.message ?? `${label} failed with ${response.status}`);
  }

  return payload;
}

async function requestJson(path, options, label) {
  const response = await fetch(path, options);
  return readJsonOrThrow(response, label);
}

export async function loadAppShellData() {
  const [healthResponse, infoResponse, sourceResponse] = await Promise.all([
    fetch("/api/health"),
    fetch("/api/app/info"),
    fetch("/api/source")
  ]);

  const [health, infoPayload, sourcePayload] = await Promise.all([
    readJsonOrThrow(healthResponse, "Health check"),
    readJsonOrThrow(infoResponse, "App info"),
    readJsonOrThrow(sourceResponse, "Source info")
  ]);

  return {
    health,
    info: {
      ...fallbackInfo,
      ...infoPayload,
      database: {
        ...fallbackInfo.database,
        ...infoPayload.database
      },
      queue: {
        ...fallbackInfo.queue,
        ...infoPayload.queue
      }
    },
    source: sourcePayload.source ?? null
  };
}

export function fetchTree() {
  return requestJson("/api/tree", undefined, "Tree load");
}

export function fetchFiles(directory = "") {
  const query = directory ? `?directory=${encodeURIComponent(directory)}` : "";
  return requestJson(`/api/files${query}`, undefined, "File list");
}

export function fetchConversionProfiles() {
  return requestJson("/api/conversion-profiles", undefined, "Conversion profiles");
}

export function fetchSettings() {
  return requestJson("/api/settings", undefined, "Settings load");
}

export function fetchProviderSettings() {
  return requestJson("/api/settings/providers", undefined, "Provider settings load");
}

export function saveSettings(payload) {
  return requestJson(
    "/api/settings",
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    },
    "Save settings"
  );
}

export function saveProviderSettings(providers) {
  return requestJson(
    "/api/settings/providers",
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ providers })
    },
    "Save provider settings"
  );
}

export function fetchPreviewLayouts() {
  return requestJson("/api/preview-layouts", undefined, "Preview presets");
}

export function createPreviewLayout(payload) {
  return requestJson(
    "/api/preview-layouts",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    },
    "Create preview preset"
  );
}

export function updatePreviewLayout(presetId, payload) {
  return requestJson(
    `/api/preview-layouts/${encodeURIComponent(presetId)}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    },
    "Update preview preset"
  );
}

export function generateLivePreview(payload) {
  return requestJson(
    "/api/preview-layouts/preview",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    },
    "Live preview"
  );
}

export function fetchJobs(limit = 20) {
  return requestJson(`/api/jobs?limit=${limit}`, undefined, "Jobs load");
}

export function fetchJob(jobId) {
  return requestJson(`/api/jobs/${encodeURIComponent(jobId)}`, undefined, "Job detail");
}

export function fetchJobItems(jobId) {
  return requestJson(`/api/jobs/${encodeURIComponent(jobId)}/items`, undefined, "Job items");
}

export function fetchLogs({ jobId, limit = 100 } = {}) {
  const params = new URLSearchParams();
  if (jobId) {
    params.set("job_id", jobId);
  }
  params.set("limit", String(limit));
  const query = params.toString();
  return requestJson(`/api/logs${query ? `?${query}` : ""}`, undefined, "Log load");
}

export function saveSource(payload) {
  return requestJson(
    "/api/source",
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    },
    "Save source"
  );
}

export function testSourceConnection(payload) {
  return requestJson(
    "/api/source/test-connection",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    },
    "Source test"
  );
}

export function reconnectSource() {
  return requestJson(
    "/api/source/reconnect",
    {
      method: "POST"
    },
    "Source reconnect"
  );
}

export function createScanSourceJob() {
  return requestJson(
    "/api/jobs/scan-source",
    {
      method: "POST"
    },
    "Scan source"
  );
}

export function createRescanDirectoryJob(relativePath) {
  return requestJson(
    "/api/jobs/rescan-directory",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ relative_path: relativePath })
    },
    "Rescan directory"
  );
}

export function createConvertDirectoryJob(relativePath, { profileId, mode } = {}) {
  return requestJson(
    "/api/jobs/convert-directory",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ relative_path: relativePath, profile_id: profileId ?? null, mode: mode ?? "production" })
    },
    "Convert directory"
  );
}

export function createConvertFileJob(fileId, { profileId, mode } = {}) {
  return requestJson(
    "/api/jobs/convert-file",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ file_id: fileId, profile_id: profileId ?? null, mode: mode ?? "production" })
    },
    "Convert file"
  );
}

export function createPreviewDirectoryJob(relativePath) {
  return requestJson(
    "/api/jobs/preview-directory",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ relative_path: relativePath })
    },
    "Preview directory"
  );
}

export function createPreviewFileJob(fileId) {
  return requestJson(
    "/api/jobs/preview-file",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ file_id: fileId })
    },
    "Preview file"
  );
}

export function createTagFileJob(fileId) {
  return requestJson(
    "/api/jobs/tag-file",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ file_id: fileId })
    },
    "Tag file"
  );
}

export function fetchFilePreview(fileId) {
  return requestJson(`/api/files/${encodeURIComponent(fileId)}/preview`, undefined, "File preview");
}

export function fetchDirectoryPreview(relativePath = "") {
  const query = `?relative_path=${encodeURIComponent(relativePath)}`;
  return requestJson(`/api/directories/preview${query}`, undefined, "Directory preview");
}

export function fetchFileTags(fileId) {
  return requestJson(`/api/files/${encodeURIComponent(fileId)}/tags`, undefined, "File tags");
}

export function fetchFileDetail(fileId) {
  return requestJson(`/api/files/${encodeURIComponent(fileId)}`, undefined, "File detail");
}

export function fetchFilePlayback(fileId) {
  return requestJson(`/api/files/${encodeURIComponent(fileId)}/playback`, undefined, "File playback");
}

export function fetchPlaybackSettings() {
  return requestJson("/api/settings/playback", undefined, "Playback settings load");
}

export function savePlaybackSettings(payload) {
  return requestJson(
    "/api/settings/playback",
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    },
    "Save playback settings"
  );
}

export function createTuneFileJob(fileId, sweep) {
  return requestJson(
    "/api/jobs/tune-file",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ file_id: fileId, sweep })
    },
    "Tune file"
  );
}

export function promoteTuneVariant({ jobId, itemId, name, isDefault }) {
  return requestJson(
    "/api/conversion-profiles/promote-tune",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ job_id: jobId, item_id: itemId, name, is_default: Boolean(isDefault) })
    },
    "Promote tuning result"
  );
}

export function createTagDirectoryJob(relativePath) {
  return requestJson(
    "/api/jobs/tag-directory",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ relative_path: relativePath })
    },
    "Tag directory"
  );
}

export function cancelJob(jobId) {
  return requestJson(
    `/api/jobs/${encodeURIComponent(jobId)}/cancel`,
    {
      method: "POST"
    },
    "Cancel job"
  );
}

export function restartJob(jobId) {
  return requestJson(
    `/api/jobs/${encodeURIComponent(jobId)}/restart`,
    {
      method: "POST"
    },
    "Restart job"
  );
}

export { fallbackInfo };
