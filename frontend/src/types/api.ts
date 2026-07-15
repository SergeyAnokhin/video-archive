export interface HealthResponse {
  status: string
}

export interface FfmpegInfo {
  available: boolean
  version: string | null
  path: string | null
}

export interface DatabaseInfo {
  status: string
  schema_version: number | null
}

export type JobStatus = 'queued' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled'
export type JobItemStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | 'skipped'
export type LogLevel = 'debug' | 'info' | 'warning' | 'error'

export interface JobSummary {
  id: string
  job_type: string
  scope_type: string
  scope_ref: string | null
  status: JobStatus
  parameters: Record<string, unknown>
  started_at: string | null
  finished_at: string | null
  summary_message: string | null
  total_items: number | null
  failed_item_count: number
  created_at: string
  updated_at: string
}

export interface JobItem {
  id: string
  job_id: string
  file_id: string | null
  item_key: string | null
  status: JobItemStatus
  step_name: string | null
  message: string | null
  started_at: string | null
  finished_at: string | null
  output_ref: string | null
}

export interface LogEvent {
  id: string
  job_id: string | null
  file_id: string | null
  level: LogLevel
  event_type: string
  message: string
  payload: Record<string, unknown> | null
  created_at: string
}

export interface QueueInfo {
  current_job: JobSummary | null
}

export interface SourceSummary {
  id: string
  name: string
  protocol: string
  root_path: string
  last_scan_at: string | null
}

export interface AppInfoResponse {
  app_version: string
  source: SourceSummary | null
  database: DatabaseInfo
  queue: QueueInfo
  ffmpeg: FfmpegInfo
}

export type SourceProtocol = 'local' | 'smb'

export interface SourceConfig {
  id: string
  name: string
  protocol: string
  host: string | null
  port: number | null
  root_path: string
  is_active: boolean
  created_at: string
  updated_at: string
  last_connected_at: string | null
  last_scan_at: string | null
}

export interface TestConnectionResult {
  ok: boolean
  message: string | null
}

export interface PreviewCacheStats {
  size_bytes: number
  file_count: number
}

export interface SavedSource extends SourceConfig {
  preview_cache: PreviewCacheStats
}

export interface DirectoryStatus {
  total_supported_files: number
  converted_count: number
  preview_count: number
  conversion_complete: boolean
  preview_complete: boolean
  total_size_bytes: number
  top_variant_tags: VariantTag[]
}

export interface FolderTagSummary {
  tag_id: string
  display_name: string
  color: string
  usage_count: number
}

export interface TreeNode {
  path: string
  name: string
  status?: DirectoryStatus
  top_tags?: FolderTagSummary[]
  children: TreeNode[]
}

export interface DirectoryEntry {
  path: string
  name: string
  status?: DirectoryStatus
  top_tags?: FolderTagSummary[]
  has_folder_preview: boolean
  is_favorite: boolean
}

export interface FavoriteDirectory {
  path: string
  name: string
}

export interface VariantTag {
  param: 'dimension' | 'crf' | 'codec'
  value: number | string
}

export interface FileTagSummary {
  tag_id: string
  display_name: string
  color: string
  score: number
  provider_name: string | null
  model_name: string | null
}

export interface FileEntry {
  id: string
  file_name: string
  extension: string
  size_bytes: number
  modified_at: string | null
  is_video_supported: boolean
  is_image_supported: boolean
  has_preview_asset: boolean
  converted_at: string | null
  tagged_at: string | null
  is_variant: boolean
  is_original: boolean
  duration_seconds: number | null
  variant_tags?: VariantTag[]
  ai_tags?: FileTagSummary[]
}

export interface DirectoryChildrenResponse {
  path: string
  directories: DirectoryEntry[]
  files: FileEntry[]
}

export type ConversionMode = 'production' | 'test'

export interface ConversionProfile {
  id: string
  name: string
  is_default: boolean
  video_codec: string
  container: string
  max_dimension: number | null
  crf: number
  drop_audio: boolean
  extra_encoder_args: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface VariantOverride {
  max_dimension?: number
  crf?: number
  video_codec?: string
}

export interface FileMediaInfo {
  width: number | null
  height: number | null
  aspect_ratio: string | null
  video_codec: string | null
  format_name: string | null
  duration: number | null
  bit_rate: number | null
  conversion_profile: ConversionProfile | null
}

export type TimelineFlow = 'row' | 'column' | 'shuffle'
export type AspectRatioMode = 'standard' | 'phone-portrait' | 'phone-landscape' | 'ultra-wide' | 'custom'

export interface EnlargedTile {
  row: number
  col: number
  span: 2 | 3
}

export interface LayoutTile {
  row: number
  col: number
  span: number
  type: 'small' | 'enlarged'
}

export interface PreviewLayoutPreset {
  id: string
  name: string
  grid_rows: number
  grid_cols: number
  timeline_flow: TimelineFlow
  identity_diversity_enabled: boolean
  layout_definition: EnlargedTile[]
  is_builtin: boolean
  is_default: boolean
  created_at: string
  updated_at: string
}

export type AnimatedSourceMode = 'frame' | 'clip'
export type AnimatedTransition = 'cut' | 'crossfade'

export interface PreviewSettings {
  aspect_ratio: AspectRatioMode
  aspect_ratio_custom_width: number | null
  aspect_ratio_custom_height: number | null
  folder_preview_frame_count: number
  gif_max_width: number
  gif_colors: number
  animated_source_mode: AnimatedSourceMode
  animated_segment_seconds: number
  animated_transition: AnimatedTransition
  updated_at: string
}

export interface LayoutPreviewResponse {
  grid_rows: number
  grid_cols: number
  tiles: LayoutTile[]
  frame_count: number
}

export interface Tag {
  id: string
  tag_key: string
  display_name: string
  is_active: boolean
  is_ai_vocabulary: boolean
  is_user_defined: boolean
  sort_order: number
  color: string
  created_at: string
  updated_at: string
}

export interface FileTagAssignment {
  tag_id: string
  display_name: string
  color: string
  score: number
  provider_name: string | null
  model_name: string | null
  assigned_at: string
}

export interface TaggingSettings {
  sample_frame_count: number
  combine_into_collage: boolean
  top_tag_count: number
  image_resolution: number
  request_timeout_seconds: number
  updated_at: string
}

export type ProviderType = 'openrouter' | 'gemini' | 'fal' | 'mistral'

export interface ProviderEntry {
  id: string
  provider_type: ProviderType
  display_name: string
  enabled: boolean
  vision_model: string | null
  text_model: string | null
  batch_enabled: boolean
  sort_order: number
  has_api_key: boolean
  key_suffix: string | null
  created_at: string
  updated_at: string
}

export interface TagLabRankedTag {
  tag_id: string
  display_name: string
  color: string
  score: number
}

export interface TagLabImage {
  data_url: string
  width: number
  height: number
}

export interface TagLabRunResult {
  run_id: string
  images: TagLabImage[]
  prompt: string
  raw_response: string | null
  raw_full_response: Record<string, unknown> | null
  tokens_in: number | null
  tokens_out: number | null
  estimated_cost_usd: number | null
  provider_type: ProviderType
  model_name: string | null
  tags: TagLabRankedTag[]
}

export interface TagLabPreparedResult {
  images: TagLabImage[]
  prompt: string
}

export type ModelPricingSource = 'manual' | 'openrouter_api'

export interface ModelPricing {
  provider_type: ProviderType
  model_name: string
  input_per_million: number | null
  output_per_million: number | null
  source: ModelPricingSource
  updated_at: string
}

export interface ModelStats {
  provider_type: ProviderType
  model_name: string | null
  likes: number
  dislikes: number
  runs_total: number
  applied_count: number
  not_applied_count: number
  applied_unchanged_count: number
  applied_changed_count: number
}

export interface BatchSubmission {
  id: string
  job_id: string
  provider_type: ProviderType
  model_name: string | null
  item_count: number
  status: string
  created_at: string
}

export interface ProviderUsageSummary {
  provider_type: ProviderType
  model_name: string | null
  call_count: number
  success_count: number
  total_items: number
  total_tokens_in: number | null
  total_tokens_out: number | null
  total_estimated_cost_usd: number | null
  last_used_at: string
}

export type PlaybackMode = 'stream' | 'direct_link'

export interface PlaybackSettings {
  mode: PlaybackMode
  updated_at: string
}

export interface PlaybackInfo {
  mode: PlaybackMode
  stream_url: string
  direct_path: string
}

export interface BackupSummary {
  id: string
  filename: string
  backup_id: string
  created_at: string
  app_version: string
  schema_version: number
  source_name: string
  includes_secrets: boolean
  size_bytes: number | null
}

export interface BackupSettings {
  retention_count: number
  updated_at: string
}

export interface PerformanceSettings {
  parallel_workers: number
  updated_at: string
}

export interface NetworkInfo {
  lan_addresses: string[]
  frontend_port: number
  backend_port: number
}

// Single source of truth for the theme list: both the top bar's cycle toggle
// and the Settings picker iterate this value, so adding a preset here (plus
// its icon entries and `theme.*` locale keys) surfaces it everywhere at once.
export const THEME_PRESETS = [
  'strict',
  'playful',
  'casino',
  'neon',
  'toxic',
  'cyber',
  'vivid',
  'mono',
] as const
export type ThemePreset = (typeof THEME_PRESETS)[number]

export interface InterfaceSettings {
  language: 'en' | 'ru'
  theme_preset: ThemePreset
  profile_a_saturation: number
  profile_a_blur: number
  profile_a_brightness: number
  profile_a_contrast: number
  profile_a_sepia: number
  profile_a_hue_rotate: number
  profile_b_saturation: number
  profile_b_blur: number
  profile_b_brightness: number
  profile_b_contrast: number
  profile_b_sepia: number
  profile_b_hue_rotate: number
  search_tag_limit: number
  search_file_limit: number
  search_dir_limit: number
  updated_at: string
}

// Scoped library search (user request): per-group caps for the grouped
// search suggestions/results (found-in-tags / file names / directory names).
export interface SearchLimits {
  tags: number
  files: number
  dirs: number
}

export interface DirectorySearchResponse {
  directories: DirectoryEntry[]
}

export interface SimilarFile {
  file_id: string
  relative_path: string
  file_name: string
  distance: number
}
