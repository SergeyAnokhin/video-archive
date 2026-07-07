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
  aspect_ratio_preset: "s24",
  layout_preset_id: "default-preview-grid"
};

export const defaultPlaybackSettings = {
  mode: "embedded",
  external_strategy: "file_uri"
};

export const defaultTaggingSettings = {
  provider_id: "",
  sample_count: 9,
  combine_frames: true,
  prefer_batch: true,
  vocabulary: []
};

export const providerOptions = [
  { value: "openrouter", label: "OpenRouter" },
  { value: "gemini", label: "Google Gemini" },
  { value: "fal", label: "FAL" },
  { value: "mistral", label: "Mistral" }
];

const providerDefaultsByType = {
  openrouter: { vision_model: "", text_model: "", prefer_batch: true },
  gemini: { vision_model: "gemini-2.0-flash", text_model: "", prefer_batch: true },
  fal: { vision_model: "", text_model: "", prefer_batch: true },
  mistral: { vision_model: "pixtral-large-latest", text_model: "", prefer_batch: true }
};

export const defaultProviderSettings = [];

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
  parameter: "quality",
  dimensionMin: "800",
  dimensionMax: "1000",
  dimensionStep: "100",
  qualityMin: "20",
  qualityMax: "28",
  qualityStep: "4",
  fixedDimension: "1000",
  fixedQuality: "24",
  fixedCodec: "h265",
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
    provider_id: typeof settings?.provider_id === "string" ? settings.provider_id : "",
    vocabulary: Array.isArray(settings?.vocabulary)
      ? settings.vocabulary.map((entry) => (typeof entry === "string" ? entry : entry.display_name)).filter(Boolean)
      : []
  };
}

export function buildProviderDraft(providerType = "gemini") {
  const defaults = providerDefaultsByType[providerType] ?? providerDefaultsByType.gemini;
  return {
    id: `provider-${crypto.randomUUID()}`,
    order_index: 0,
    provider: providerType,
    label: providerOptions.find((entry) => entry.value === providerType)?.label ?? providerType,
    enabled: true,
    vision_model: defaults.vision_model,
    text_model: defaults.text_model,
    prefer_batch: defaults.prefer_batch,
    api_key: "",
    api_key_configured: false,
    available_models: [],
    is_loading_models: false
  };
}

export function normalizeProviderSettings(settings) {
  if (!Array.isArray(settings)) {
    return [];
  }
  return settings.map((entry, index) => ({
    ...buildProviderDraft(entry?.provider ?? "gemini"),
    ...entry,
    order_index: typeof entry?.order_index === "number" ? entry.order_index : index,
    api_key: "",
    available_models: Array.isArray(entry?.available_models) ? entry.available_models : [],
    is_loading_models: false
  }));
}

export function getProviderDefaults(providerType) {
  return providerDefaultsByType[providerType] ?? providerDefaultsByType.gemini;
}

export function getProviderLabel(providerType) {
  return providerOptions.find((entry) => entry.value === providerType)?.label ?? providerType;
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

function parsePositiveInteger(value, label) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 1) {
    throw new Error(`${label} must be a positive integer.`);
  }
  return parsed;
}

function buildInclusiveRange({ minValue, maxValue, stepValue, label }) {
  const min = parsePositiveInteger(minValue, `${label} min`);
  const max = parsePositiveInteger(maxValue, `${label} max`);
  const step = parsePositiveInteger(stepValue, `${label} step`);
  if (max < min) {
    throw new Error(`${label} max must be greater than or equal to min.`);
  }
  const values = [];
  for (let current = min; current <= max; current += step) {
    values.push(current);
  }
  if (values[values.length - 1] !== max) {
    values.push(max);
  }
  return [...new Set(values)];
}

export function buildTuneSweep(draft) {
  const codecs = Object.entries(draft.codecs)
    .filter(([, enabled]) => enabled)
    .map(([codec]) => codec);
  const parameter = draft.parameter ?? "quality";
  const fixedDimension = parsePositiveInteger(draft.fixedDimension, "Fixed max side");
  const fixedQuality = String(parsePositiveInteger(draft.fixedQuality, "Fixed CRF"));
  let dimensions = [fixedDimension];
  let qualityValues = [fixedQuality];
  let selectedCodecs = [draft.fixedCodec || "h265"];

  if (parameter === "dimension") {
    dimensions = buildInclusiveRange({
      minValue: draft.dimensionMin,
      maxValue: draft.dimensionMax,
      stepValue: draft.dimensionStep,
      label: "Max side"
    });
  } else if (parameter === "quality") {
    qualityValues = buildInclusiveRange({
      minValue: draft.qualityMin,
      maxValue: draft.qualityMax,
      stepValue: draft.qualityStep,
      label: "CRF"
    }).map((value) => String(value));
  } else if (parameter === "codec") {
    if (!codecs.length) {
      throw new Error("Select at least one codec for tuning.");
    }
    selectedCodecs = codecs;
  } else {
    throw new Error("Unsupported tuning parameter.");
  }

  const variantCount = dimensions.length * qualityValues.length * selectedCodecs.length;
  if (variantCount > 24) {
    throw new Error("Tuning sweep is too large. Keep it to 24 variants or fewer.");
  }
  return {
    dimensions,
    quality_values: qualityValues,
    codecs: selectedCodecs,
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
