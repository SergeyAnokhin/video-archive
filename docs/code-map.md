# Code Map

This repository currently contains the first implementation skeleton for Video Archive: a root npm orchestrator, a Vite-based React frontend, and a minimal Python HTTP backend. Use this map to find the startup flow and the smallest files to extend first.

| Path | Role |
| --- | --- |
| [`package.json`](../package.json) | Root developer entrypoint that starts frontend and backend together with `npm run dev`. |
| [`frontend/package.json`](../frontend/package.json) | Frontend scripts and React/Vite dependencies. |
| [`frontend/vite.config.js`](../frontend/vite.config.js) | Local dev server config and `/api` proxy to the backend. |
| [`frontend/src/App.jsx`](../frontend/src/App.jsx) | Minimal app shell that verifies backend connectivity and exposes the current bootstrap status. |
| [`frontend/src/styles.css`](../frontend/src/styles.css) | Initial dark-theme styling for the shell UI. |
| [`backend/package.json`](../backend/package.json) | Backend-local `npm run dev` wrapper for the Python server on Windows terminals. |
| [`backend/app/main.py`](../backend/app/main.py) | Stdlib HTTP backend with the initial `/api/health` and `/api/app/info` endpoints. |
| [`README.md`](../README.md) | Local setup and exact Windows terminal commands for combined and independent startup. |
