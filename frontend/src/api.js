const fallbackInfo = {
  version: "0.1.0",
  active_source: null,
  database: {
    status: "not_configured",
    schema_version: null
  },
  queue: {
    status: "idle",
    queued_jobs: 0,
    running_jobs: 0
  }
};

async function readJsonOrThrow(response, label) {
  if (!response.ok) {
    throw new Error(`${label} failed with ${response.status}`);
  }

  return response.json();
}

export async function loadAppShellData() {
  const [healthResponse, infoResponse, sourceResponse] = await Promise.all([
    fetch("/api/health"),
    fetch("/api/app/info"),
    fetch("/api/source")
  ]);

  const [health, infoPayload, sourcePayload] = await Promise.all([
    readJsonOrThrow(healthResponse, "Health check"),
    readJsonOrThrow(infoResponse, "App info"),
    readJsonOrThrow(sourceResponse, "Source info")
  ]);

  return {
    health,
    info: {
      ...fallbackInfo,
      ...infoPayload,
      database: {
        ...fallbackInfo.database,
        ...infoPayload.database
      },
      queue: {
        ...fallbackInfo.queue,
        ...infoPayload.queue
      }
    },
    source: sourcePayload.source ?? null
  };
}

export { fallbackInfo };
