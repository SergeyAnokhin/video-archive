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

export interface SourceConfig {
  id: string
  name: string
  protocol: string
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
