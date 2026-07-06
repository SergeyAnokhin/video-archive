# Dev Entrypoints

Use this page when the question is "what should I open or run first?" Keep the route narrow before opening the larger shell or service files.

## Read First

| Task | Read first | Only then follow |
| --- | --- | --- |
| Localization or RU/EN copy | [`../frontend/src/i18n.js`](../frontend/src/i18n.js) | `rg "sectionPrefix\\." ../frontend/src/i18n.js` for the exact block instead of reading the full file, then open [`../frontend/src/components/`](../frontend/src/components/) only if the key owner is unclear. |
| Visual mode or theme tokens | [`../frontend/src/styles/theme.css`](../frontend/src/styles/theme.css) | [`../frontend/src/styles.css`](../frontend/src/styles.css) for layout/modal selectors that consume the tokens. |
| Preview aspect ratio, tile ordering, or layout math | [`../backend/app/preview_layout.py`](../backend/app/preview_layout.py) | [`../backend/app/preview_service.py`](../backend/app/preview_service.py) only if the change also affects DB payloads, sampling orchestration, or asset persistence. |
| Local source settings or repo test archive flow | [`../frontend/src/features/source/SourceSettingsSection.jsx`](../frontend/src/features/source/SourceSettingsSection.jsx) | [`../frontend/src/features/source/sourceHelpers.js`](../frontend/src/features/source/sourceHelpers.js), then [`../backend/app/source_service.py`](../backend/app/source_service.py) if validation or browse behavior changes. |

## Canonical Commands

| Goal | Command | Why this one |
| --- | --- | --- |
| Start the full local app | `npm.cmd run dev` | Starts both frontend and backend with the repo's Windows entrypoint. |
| Frontend verification after UI-only changes | `npm.cmd run build --prefix frontend` | Fastest durable check for component, modal, and CSS splits. |
| Full backend regression pass | `npm.cmd run test --prefix backend` | Uses the repo-root-safe unittest discovery path. |
| Preview helper spot check | `cd backend; python -m unittest discover -s tests -t . -p "test_preview*.py"` | Narrowest working check for layout/sampling changes without re-reading the whole backend suite output. |

## Practical Rules

- If the change is only presentational, start in the extracted modal, settings section, or layout component before opening [`../frontend/src/App.jsx`](../frontend/src/App.jsx).
- If the change is only preview layout math, do not open the full preview service first; inspect [`../backend/app/preview_layout.py`](../backend/app/preview_layout.py) and its tests first.
- If the change is only theme work, do not scan the full stylesheet first; inspect [`../frontend/src/styles/theme.css`](../frontend/src/styles/theme.css) and grep the consuming selector in [`../frontend/src/styles.css`](../frontend/src/styles.css).
