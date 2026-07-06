export function formatStatusLabel(value, t) {
  return t(`status.${value}`).replaceAll("_", " ");
}

export function formatBytes(value) {
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

export function formatDate(value, locale) {
  if (!value) {
    return "-";
  }

  return new Date(value).toLocaleString(locale === "ru" ? "ru-RU" : "en-US");
}

export function formatProfileLabel(profile, t) {
  const parts = [`${profile.video_codec.toUpperCase()} -> ${profile.container.toUpperCase()}`];
  if (profile.max_dimension) {
    parts.push(`${t("profiles.maxDimension")} ${profile.max_dimension}px`);
  }
  if (profile.quality_value) {
    parts.push(`${(profile.quality_mode || "quality").toUpperCase()} ${profile.quality_value}`);
  }
  parts.push(profile.drop_audio ? t("profiles.dropAudio") : "audio");
  return `${profile.name} (${parts.join(", ")})`;
}

export function formatJobScope(job, t) {
  if (!job) {
    return "-";
  }
  if (job.scope_type === "source") {
    return t("app.activeSource");
  }
  if (job.scope_type === "directory") {
    return job.scope_ref || t("app.libraryRoot");
  }
  return job.scope_ref || "-";
}

export function formatJobTypeLabel(value, t) {
  return t(`jobTypes.${value}`);
}

export function formatConfidence(value) {
  if (!Number.isFinite(value)) {
    return "-";
  }
  return `${Math.round(value * 100)}%`;
}

export function renderIndicatorBadges(indicators, t) {
  return [
    indicators?.conversion
      ? { key: "conversion", label: t("directory.convertBadge"), state: indicators.conversion.state, title: indicators.conversion.message }
      : null,
    indicators?.preview
      ? { key: "preview", label: t("directory.previewBadge"), state: indicators.preview.state, title: indicators.preview.message }
      : null
  ].filter(Boolean);
}
