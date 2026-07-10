export interface PreviewStyleProfile {
  saturation: number
  blur: number
  brightness: number
  contrast: number
  sepia: number
  hueRotate: number
}

export const DEFAULT_PREVIEW_PROFILE_A: PreviewStyleProfile = {
  saturation: 100,
  blur: 0,
  brightness: 100,
  contrast: 100,
  sepia: 0,
  hueRotate: 0,
}

export const DEFAULT_PREVIEW_PROFILE_B: PreviewStyleProfile = {
  saturation: 20,
  blur: 16,
  brightness: 100,
  contrast: 100,
  sepia: 0,
  hueRotate: 0,
}

export function previewFilterCss(profile: PreviewStyleProfile): string {
  return (
    `saturate(${profile.saturation / 100}) blur(${profile.blur}px) ` +
    `brightness(${profile.brightness / 100}) contrast(${profile.contrast / 100}) ` +
    `sepia(${profile.sepia / 100}) hue-rotate(${profile.hueRotate}deg)`
  )
}
