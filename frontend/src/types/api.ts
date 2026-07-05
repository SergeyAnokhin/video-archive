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

export interface AppInfoResponse {
  app_version: string
  source: unknown | null
  database: DatabaseInfo
  queue: QueueInfo
  ffmpeg: FfmpegInfo
}
