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

export type JobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
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

export interface DirectoryStatus {
  total_supported_files: number
  converted_count: number
  preview_count: number
  conversion_complete: boolean
  preview_complete: boolean
}

export interface TreeNode {
  path: string
  name: string
  status?: DirectoryStatus
  children: TreeNode[]
}

export interface DirectoryEntry {
  path: string
  name: string
  status?: DirectoryStatus
  has_folder_preview: boolean
}

export interface FileEntry {
  id: string
  file_name: string
  extension: string
  size_bytes: number
  modified_at: string | null
  is_video_supported: boolean
  has_preview_asset: boolean
  converted_at: string | null
  tagged_at: string | null
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

export type TimelineFlow = 'row' | 'column' | 'shuffle'
export type AspectRatioMode = 'standard' | 'phone-portrait' | 'ultra-wide' | 'custom'

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

export interface PreviewSettings {
  aspect_ratio: AspectRatioMode
  aspect_ratio_custom_width: number | null
  aspect_ratio_custom_height: number | null
  folder_preview_frame_count: number
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
  sort_order: number
  created_at: string
  updated_at: string
}

export interface FileTagAssignment {
  tag_id: string
  display_name: string
  score: number
  provider_name: string | null
  model_name: string | null
  assigned_at: string
}

export interface TaggingSettings {
  sample_frame_count: number
  combine_into_collage: boolean
  top_tag_count: number
  default_provider: string | null
  default_vision_model: string | null
  updated_at: string
}

export type ProviderName = 'openrouter' | 'gemini' | 'fal' | 'mistral'

export interface ProviderConfig {
  provider_name: ProviderName
  enabled: boolean
  vision_model: string | null
  text_model: string | null
  batch_enabled: boolean
  has_api_key: boolean
  updated_at: string
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

export type ThemePreset = 'strict' | 'playful'

export interface InterfaceSettings {
  language: 'en' | 'ru'
  theme_preset: ThemePreset
  updated_at: string
}

export interface SimilarFile {
  file_id: string
  relative_path: string
  file_name: string
  distance: number
}
