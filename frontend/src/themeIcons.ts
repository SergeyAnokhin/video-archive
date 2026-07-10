import { Biohazard, Cpu, Dices, Flame, Palette, Snowflake, Sparkles, Zap } from 'lucide-react'
import type { ThemePreset } from './types/api'

// Single source of truth for theme icons, read by both the top-bar cycle
// toggle and the Settings picker (mirrors the `THEME_PRESETS` comment in
// types/api.ts) -- used to live duplicated in both components.
export const THEME_ICON: Record<ThemePreset, typeof Palette> = {
  strict: Palette,
  playful: Sparkles,
  casino: Dices,
  neon: Zap,
  toxic: Biohazard,
  cyber: Cpu,
  vivid: Flame,
  mono: Snowflake,
}
