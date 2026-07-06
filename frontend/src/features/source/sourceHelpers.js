export const emptySourceForm = {
  name: "",
  protocol: "smb",
  host: "",
  port: "",
  root_path: "",
  username: "",
  password: ""
};

export const emptyLocalDirectoryBrowser = {
  path: "",
  parent_path: null,
  directories: [],
  favorites: []
};

export const defaultPreviewSettings = {
  sample_count: 9,
  large_tile_count: 2,
  timeline_flow: "row",
  identity_diversity_enabled: true,
  aspect_ratio_preset: "video",
  layout_preset_id: "default-preview-grid"
};

export const defaultPlaybackSettings = {
  mode: "embedded",
  external_strategy: "file_uri"
};

export const defaultTaggingSettings = {
  provider: "openrouter",
  sample_count: 9,
  combine_frames: true,
  prefer_batch: true,
  vocabulary: []
};

export const defaultProviderSettings = [
  { provider: "openrouter", enabled: false, vision_model: "", text_model: "", prefer_batch: true, api_key: "", api_key_configured: false },
  { provider: "gemini", enabled: false, vision_model: "gemini-2.0-flash", text_model: "", prefer_batch: true, api_key: "", api_key_configured: false },
  { provider: "fal", enabled: false, vision_model: "", text_model: "", prefer_batch: true, api_key: "", api_key_configured: false },
  { provider: "mistral", enabled: false, vision_model: "pixtral-large-latest", text_model: "", prefer_batch: true, api_key: "", api_key_configured: false }
];

export const emptyProfileDraft = {
  name: "",
  video_codec: "h265",
  container: "mp4",
  max_dimension: "",
  quality_mode: "crf",
  quality_value: "",
  drop_audio: true,
  extra_encoder_args: "",
  is_default: false
};

export const emptyLogFilters = {
  jobId: "",
  fileId: "",
  level: ""
};

export const defaultTuneDraft = {
  dimensionsText: "1000, 900, 800",
  qualitiesText: "20, 24, 28",
  codecs: {
    h264: false,
    h265: true,
    av1: false
  },
  dropAudio: true
};

export function toTaggingForm(settings) {
  return {
    ...defaultTaggingSettings,
    ...settings,
    vocabulary: Array.isArray(settings?.vocabulary)
      ? settings.vocabulary.map((entry) => (typeof entry === "string" ? entry : entry.display_name)).filter(Boolean)
      : []
  };
}

export function flattenTree(nodes, depth = 0) {
  return nodes.flatMap((node) => [
    { ...node, depth },
    ...(node.children ? flattenTree(node.children, depth + 1) : [])
  ]);
}

export function toSourceForm(source) {
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

export function toSourcePayload(form) {
  const isLocal = form.protocol === "local";
  return {
    name: form.name.trim(),
    protocol: form.protocol,
    host: isLocal ? null : form.host.trim(),
    port: isLocal || form.port === "" ? null : Number(form.port),
    root_path: form.root_path.trim(),
    username: isLocal ? null : form.username.trim() || null,
    password: isLocal ? null : form.password.trim() || null
  };
}

export function isLocalProtocol(protocol) {
  return protocol === "local";
}

export function formatSourceSummary(source, t = null) {
  if (!source) {
    return t ? t("app.noActiveSource") : "Configure one active source to enable scan and browsing";
  }
  if (isLocalProtocol(source.protocol)) {
    return `LOCAL - ${source.root_path}`;
  }
  return `${source.protocol.toUpperCase()} - ${source.host} - ${source.root_path}`;
}

export function formatDirectoryLabel(path, t = null) {
  return path ? path : t ? t("app.libraryRoot") : "Library root";
}

function parseCommaNumberList(value) {
  return value
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean)
    .map((entry) => Number(entry))
    .filter((entry) => Number.isInteger(entry) && entry > 0);
}

function parseCommaStringList(value) {
  return value
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

export function buildTuneSweep(draft) {
  const codecs = Object.entries(draft.codecs)
    .filter(([, enabled]) => enabled)
    .map(([codec]) => codec);
  return {
    dimensions: parseCommaNumberList(draft.dimensionsText),
    quality_values: parseCommaStringList(draft.qualitiesText),
    codecs: codecs.length ? codecs : ["h265"],
    drop_audio: draft.dropAudio
  };
}

export function buildProfilePayloadFromVariant(name, variant, isDefault = false) {
  return {
    name,
    is_default: isDefault,
    video_codec: variant.video_codec,
    container: "mp4",
    max_dimension: variant.max_dimension,
    quality_mode: variant.quality_mode,
    quality_value: variant.quality_value,
    drop_audio: variant.drop_audio,
    extra_encoder_args: ""
  };
}
