import { useEffect, useState } from "react";

const fallbackInfo = {
  version: "0.1.0",
  active_source: null,
  database: {
    status: "not_configured"
  },
  queue: {
    status: "idle",
    queued_jobs: 0,
    running_jobs: 0
  }
};

function App() {
  const [health, setHealth] = useState({ state: "loading", status: null, error: null });
  const [info, setInfo] = useState(fallbackInfo);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [healthResponse, infoResponse] = await Promise.all([
          fetch("/api/health"),
          fetch("/api/app/info")
        ]);

        if (!healthResponse.ok) {
          throw new Error(`Health check failed with ${healthResponse.status}`);
        }

        if (!infoResponse.ok) {
          throw new Error(`App info failed with ${infoResponse.status}`);
        }

        const [healthPayload, infoPayload] = await Promise.all([
          healthResponse.json(),
          infoResponse.json()
        ]);

        if (!cancelled) {
          setHealth({ state: "ready", status: healthPayload.status, error: null });
          setInfo(infoPayload);
        }
      } catch (error) {
        if (!cancelled) {
          setHealth({ state: "error", status: null, error: error.message });
        }
      }
    }

    load();

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="app-shell">
      <section className="hero">
        <p className="eyebrow">Video Archive</p>
        <h1>Initial local-first development skeleton</h1>
        <p className="summary">
          This bootstrap matches the project docs with a React frontend, a Python backend,
          root-level npm orchestration, and only the minimal bootable surfaces needed to start
          implementation.
        </p>
      </section>

      <section className="status-grid">
        <article className="panel">
          <h2>Backend health</h2>
          <p className={`status status-${health.state}`}>
            {health.state === "ready" ? `Status: ${health.status}` : "Waiting for backend"}
          </p>
          {health.error ? <p className="muted">{health.error}</p> : null}
        </article>

        <article className="panel">
          <h2>Runtime</h2>
          <dl className="meta-list">
            <div>
              <dt>Version</dt>
              <dd>{info.version}</dd>
            </div>
            <div>
              <dt>Active source</dt>
              <dd>{info.active_source?.name ?? "Not configured"}</dd>
            </div>
            <div>
              <dt>Database</dt>
              <dd>{info.database.status}</dd>
            </div>
            <div>
              <dt>Queue</dt>
              <dd>{info.queue.status}</dd>
            </div>
          </dl>
        </article>

        <article className="panel">
          <h2>Next implementation areas</h2>
          <ul className="checklist">
            <li>Remote source configuration and scan endpoints</li>
            <li>Directory tree and file browser UI</li>
            <li>Job queue, log stream, and settings screens</li>
          </ul>
        </article>
      </section>
    </main>
  );
}

export default App;

