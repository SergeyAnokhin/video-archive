export const mockTree = [
  {
    id: "library",
    name: "Library",
    path: "/",
    children: [
      {
        id: "family",
        name: "Family",
        path: "family",
        children: [
          { id: "family-2024", name: "2024", path: "family/2024" },
          { id: "family-2023", name: "2023", path: "family/2023" }
        ]
      },
      {
        id: "travel",
        name: "Travel",
        path: "travel",
        children: [
          { id: "travel-japan", name: "Japan", path: "travel/japan" },
          { id: "travel-iceland", name: "Iceland", path: "travel/iceland" }
        ]
      },
      {
        id: "projects",
        name: "Projects",
        path: "projects",
        children: [{ id: "projects-bts", name: "Behind the Scenes", path: "projects/bts" }]
      }
    ]
  }
];

export const mockFilesByDirectory = {
  "/": [
    {
      id: "overview-1",
      name: "Library Overview.mp4",
      duration: "12:48",
      size: "1.4 GB",
      modifiedAt: "2026-07-01",
      conversionState: "not_started",
      previewState: "done"
    }
  ],
  "family/2024": [
    {
      id: "family-clip-1",
      name: "Beach Sunset.mp4",
      duration: "04:36",
      size: "842 MB",
      modifiedAt: "2026-06-28",
      conversionState: "in_progress",
      previewState: "done"
    },
    {
      id: "family-clip-2",
      name: "Pool Jump.mov",
      duration: "00:54",
      size: "188 MB",
      modifiedAt: "2026-06-28",
      conversionState: "failed",
      previewState: "not_started"
    },
    {
      id: "family-clip-3",
      name: "Dinner Toast.mp4",
      duration: "02:17",
      size: "264 MB",
      modifiedAt: "2026-06-29",
      conversionState: "not_started",
      previewState: "not_started"
    }
  ],
  "family/2023": [
    {
      id: "family-2023-1",
      name: "Snow Walk.mp4",
      duration: "08:09",
      size: "1.1 GB",
      modifiedAt: "2025-12-14",
      conversionState: "done",
      previewState: "done"
    }
  ],
  "travel/japan": [
    {
      id: "travel-japan-1",
      name: "Tokyo Night Train.mp4",
      duration: "06:41",
      size: "920 MB",
      modifiedAt: "2026-05-10",
      conversionState: "not_started",
      previewState: "in_progress"
    },
    {
      id: "travel-japan-2",
      name: "Shrine Entrance.mp4",
      duration: "03:26",
      size: "410 MB",
      modifiedAt: "2026-05-11",
      conversionState: "done",
      previewState: "done"
    }
  ],
  "travel/iceland": [],
  "projects/bts": [
    {
      id: "projects-bts-1",
      name: "Lighting Pass.mov",
      duration: "11:04",
      size: "2.1 GB",
      modifiedAt: "2026-06-21",
      conversionState: "not_started",
      previewState: "not_started"
    }
  ]
};

export const mockJobs = [
  {
    id: "job-401",
    label: "Preview generation",
    target: "family/2024",
    status: "running",
    detail: "2 of 11 videos processed"
  },
  {
    id: "job-399",
    label: "Directory rescan",
    target: "travel/japan",
    status: "queued",
    detail: "Waiting for worker slot"
  },
  {
    id: "job-395",
    label: "Conversion",
    target: "Pool Jump.mov",
    status: "failed",
    detail: "Validation failed after output probe"
  },
  {
    id: "job-392",
    label: "Preview generation",
    target: "Snow Walk.mp4",
    status: "completed",
    detail: "Collage stored locally"
  }
];

export const mockLogs = [
  "12:04:18  INFO   preview job-401 sampled frame set for Beach Sunset.mp4",
  "12:04:22  WARN   conversion job-395 validation failed for Pool Jump.mov",
  "12:04:30  INFO   queue worker available for next task",
  "12:04:39  INFO   scan queued for travel/japan subtree"
];

export const settingsSections = [
  { id: "source", label: "Source" },
  { id: "profiles", label: "Profiles" },
  { id: "preview", label: "Preview" },
  { id: "playback", label: "Playback" },
  { id: "tagging", label: "Tagging" },
  { id: "providers", label: "Providers" },
  { id: "backup", label: "Backup" },
  { id: "maintenance", label: "Maintenance" }
];
