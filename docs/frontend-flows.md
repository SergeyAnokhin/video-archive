# Frontend Flows

This page is the short router for the main frontend flows that cross multiple files. Start from the first file in each row and only open the follow-up files if the change crosses the boundary described there.

| Flow | Start here | Then follow | Verify after change |
| --- | --- | --- | --- |
| Modal ownership and overlay switching | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) | [`../frontend/src/components/modals/`](../frontend/src/components/modals/), [`../frontend/src/components/settings/SettingsModal.jsx`](../frontend/src/components/settings/SettingsModal.jsx) | The intended overlay opens, closes, and returns to the right previous state. |
| Jobs flow: open jobs, poll summary, inspect items, stream events, and use quick card actions | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) | [`../frontend/src/components/modals/JobsModal.jsx`](../frontend/src/components/modals/JobsModal.jsx), [`../frontend/src/api.js`](../frontend/src/api.js), [`../backend/app/job_service.py`](../backend/app/job_service.py) | Jobs refresh, the selected job stays stable, quick log/cancel/restart actions target the right job, and new events append without duplicates. |
| Settings flow: nav, section loading, save actions | [`../frontend/src/components/settings/SettingsModal.jsx`](../frontend/src/components/settings/SettingsModal.jsx) | [`../frontend/src/components/settings/SettingsSections.jsx`](../frontend/src/components/settings/SettingsSections.jsx), [`../frontend/src/App.jsx`](../frontend/src/App.jsx), [`../frontend/src/api.js`](../frontend/src/api.js) | Opening a section still loads the matching data and save buttons update the correct backend payload. |
| Playback flow: single-click file card to modal or external open | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) | [`../frontend/src/components/layout/FileBrowserPanel.jsx`](../frontend/src/components/layout/FileBrowserPanel.jsx), [`../frontend/src/components/modals/PlaybackModal.jsx`](../frontend/src/components/modals/PlaybackModal.jsx), [`../frontend/src/components/modals/FileDetailsModal.jsx`](../frontend/src/components/modals/FileDetailsModal.jsx), [`../backend/app/playback_settings_service.py`](../backend/app/playback_settings_service.py), [`../backend/app/main.py`](../backend/app/main.py) | Embedded mode still opens immediately from the card, the modal stays video-first with close/info controls, and the info action still reaches the right file details. |
| File-card preview flow: generated preview assets into main-grid thumbnails | [`../frontend/src/components/layout/FileBrowserPanel.jsx`](../frontend/src/components/layout/FileBrowserPanel.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx), [`../backend/app/main.py`](../backend/app/main.py), [`../backend/app/preview_service.py`](../backend/app/preview_service.py) | Preview jobs update the matching file cards, cards fall back cleanly when no preview exists, and preview images load on both desktop and mobile widths. |
| Log viewer flow: open with preset filters, stream live events | [`../frontend/src/components/modals/LogViewerModal.jsx`](../frontend/src/components/modals/LogViewerModal.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx), [`../frontend/src/api.js`](../frontend/src/api.js), [`../backend/app/main.py`](../backend/app/main.py) | Filter presets still populate the modal and the stream scrolls to the newest entries. |

## Read First Shortcuts

- Localization: start in [`../frontend/src/i18n.js`](../frontend/src/i18n.js); grep the key prefix before opening any component.
- Visual mode or gradients: start in [`../frontend/src/styles/theme.css`](../frontend/src/styles/theme.css); open [`../frontend/src/styles.css`](../frontend/src/styles.css) only for consuming selectors.
- Preview layout math: start in [`../backend/app/preview_layout.py`](../backend/app/preview_layout.py); open [`../backend/app/preview_service.py`](../backend/app/preview_service.py) only if the change also touches persistence or sampling orchestration.
- Local source / test archive flow: start in [`../frontend/src/features/source/SourceSettingsSection.jsx`](../frontend/src/features/source/SourceSettingsSection.jsx), then [`../frontend/src/features/source/sourceHelpers.js`](../frontend/src/features/source/sourceHelpers.js). Save/test feedback for the active source also renders in this section, not only in the top header.

## Quick Rules

- If the change is presentational and the data already exists, start in the extracted component, not in `App.jsx`.
- If the change affects when data loads, which modal opens, or which background refresh runs, start in `App.jsx`.
- If the change touches a save button or modal action, inspect both the component and [`../frontend/src/api.js`](../frontend/src/api.js).
- If the UI and docs disagree, trust the current code path and update this file in the same change.
