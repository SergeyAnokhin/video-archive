import { tryApi } from '../api/client'
import type { PreviewLayoutPreset } from '../types/api'

// Library cards take the default layout preset's collage shape (its canvas
// width / height), so the collage and the animated GIF -- cropped to the
// same shape -- fill a card without letterboxing. Exposed as the
// `--collage-aspect` CSS variable on the document root; the last value is
// remembered so a reload doesn't flash the fallback shape first.

const STORAGE_KEY = 'video-archive:collage-aspect'

function applyAspect(aspect: string) {
  document.documentElement.style.setProperty('--collage-aspect', aspect)
}

try {
  const stored = window.localStorage.getItem(STORAGE_KEY)
  if (stored) {
    applyAspect(stored)
  }
} catch {
  // Storage unavailable: the CSS fallback applies until the presets load.
}

export function applyCollageAspectFromPresets(presets: PreviewLayoutPreset[]) {
  const preset = presets.find((candidate) => candidate.is_default) ?? presets[0]
  if (!preset) {
    return
  }
  const aspect = `${preset.canvas_width} / ${preset.canvas_height}`
  applyAspect(aspect)
  try {
    window.localStorage.setItem(STORAGE_KEY, aspect)
  } catch {
    // Not remembered across reloads; still applied for this page.
  }
}

export async function syncCollageAspect() {
  const data = await tryApi<{ presets: PreviewLayoutPreset[] }>('/api/preview-layouts')
  if (data) {
    applyCollageAspectFromPresets(data.presets)
  }
}
