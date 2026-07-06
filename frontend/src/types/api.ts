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

export interface QueueInfo {
  current_job: unknown | null
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
