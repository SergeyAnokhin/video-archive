# Code Map

This repository already has the first real browse, preview, tagging, playback, tuning, conversion, and job-monitoring flows. Use this page as a router: start from the smallest file that owns the change, then follow only the nearby files listed for that task.

## Start Here For

| Task | Read first | Then check |
| --- | --- | --- |
| Top-level library shell, selected file state, overlay switching, shared async handlers | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) | [`frontend-flows.md`](frontend-flows.md), [`frontend-map.md`](frontend-map.md) |
| App-wide formatters, status labels, size/date formatting, tree badges | [`../frontend/src/appFormatters.js`](../frontend/src/appFormatters.js) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx), [`../frontend/src/components/`](../frontend/src/components/) |
| Settings section ids and visual-mode cycling | [`../frontend/src/appShellConfig.js`](../frontend/src/appShellConfig.js) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx), [`../frontend/src/components/layout/AppHeader.jsx`](../frontend/src/components/layout/AppHeader.jsx) |
| Header / queue / settings entry buttons | [`../frontend/src/components/layout/AppHeader.jsx`](../frontend/src/components/layout/AppHeader.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) |
| Directory tree and subtree-status badges | [`../frontend/src/components/layout/DirectoryTreePanel.jsx`](../frontend/src/components/layout/DirectoryTreePanel.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx), [`../backend/app/library_service.py`](../backend/app/library_service.py) |
| File card grid, thumbnail previews, folder-level actions, selected file entry point | [`../frontend/src/components/layout/FileBrowserPanel.jsx`](../frontend/src/components/layout/FileBrowserPanel.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx), [`../backend/app/main.py`](../backend/app/main.py), [`../backend/app/preview_service.py`](../backend/app/preview_service.py) |
| Source settings form and local-folder browser | [`../frontend/src/features/source/SourceSettingsSection.jsx`](../frontend/src/features/source/SourceSettingsSection.jsx) | [`../frontend/src/features/source/sourceHelpers.js`](../frontend/src/features/source/sourceHelpers.js), [`../frontend/src/components/settings/SettingsModal.jsx`](../frontend/src/components/settings/SettingsModal.jsx), [`../backend/app/source_service.py`](../backend/app/source_service.py) |
| Non-source settings sections: preview, playback, tagging, providers, profiles | [`../frontend/src/components/settings/SettingsModal.jsx`](../frontend/src/components/settings/SettingsModal.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx), [`../frontend/src/api.js`](../frontend/src/api.js) |
| Settings section bodies and section-specific form fields | [`../frontend/src/components/settings/SettingsSections.jsx`](../frontend/src/components/settings/SettingsSections.jsx) | [`../frontend/src/components/settings/SettingsModal.jsx`](../frontend/src/components/settings/SettingsModal.jsx), [`../frontend/src/api.js`](../frontend/src/api.js) |
| File details / tune / jobs / logs / playback / conversion / promotion modals | [`../frontend/src/components/modals/`](../frontend/src/components/modals/) | [`frontend-flows.md`](frontend-flows.md), [`../frontend/src/App.jsx`](../frontend/src/App.jsx) |
| Frontend API payloads and backend contracts | [`../frontend/src/api.js`](../frontend/src/api.js) | [`../backend/app/main.py`](../backend/app/main.py) |
| Job queue behavior, item states, cancel/restart, event streams | [`../backend/app/job_service.py`](../backend/app/job_service.py) | [`../backend/app/main.py`](../backend/app/main.py), [`../frontend/src/components/modals/JobsModal.jsx`](../frontend/src/components/modals/JobsModal.jsx) |
| Playback behavior and embedded/external mode persistence | [`../backend/app/playback_settings_service.py`](../backend/app/playback_settings_service.py) | [`../frontend/src/components/settings/SettingsModal.jsx`](../frontend/src/components/settings/SettingsModal.jsx), [`../frontend/src/App.jsx`](../frontend/src/App.jsx), [`../backend/app/main.py`](../backend/app/main.py) |
| Conversion profiles, tuning promotion, conversion execution | [`../backend/app/conversion_profile_service.py`](../backend/app/conversion_profile_service.py) | [`../backend/app/conversion_service.py`](../backend/app/conversion_service.py), [`../frontend/src/App.jsx`](../frontend/src/App.jsx), [`../frontend/src/components/settings/SettingsModal.jsx`](../frontend/src/components/settings/SettingsModal.jsx) |

## Flow Routers

| If the question is about... | Read |
| --- | --- |
| which modal opens what, where selection state comes from, or what needs refreshing after an action | [`frontend-flows.md`](frontend-flows.md) |
| which frontend file is the smallest edit point | [`frontend-map.md`](frontend-map.md) |
| backend endpoints, payload shapes, and not-yet-implemented scope | [`api-spec.md`](api-spec.md) |
| persisted job/item/event behavior | [`job-model.md`](job-model.md) |
| settings meaning and stored values | [`settings-spec.md`](settings-spec.md) |
| intended screen-level product behavior | [`ui-screens.md`](ui-screens.md) |
| canonical read-first files and verification commands | [`dev-entrypoints.md`](dev-entrypoints.md) |

## Change Pairs

| If you change... | Also verify... |
| --- | --- |
| source form fields or protocol behavior | [`../frontend/src/features/source/sourceHelpers.js`](../frontend/src/features/source/sourceHelpers.js), [`../frontend/src/api.js`](../frontend/src/api.js), [`../backend/app/source_service.py`](../backend/app/source_service.py) |
| preview settings UI, file-card thumbnails, or preview storage path | [`../backend/app/preview_service.py`](../backend/app/preview_service.py), [`../backend/app/main.py`](../backend/app/main.py), [`frontend-flows.md`](frontend-flows.md) |
| preview aspect ratio, tile layout, shuffle/column ordering, or detector resize helpers | [`../backend/app/preview_layout.py`](../backend/app/preview_layout.py), [`../backend/tests/test_preview_layout.py`](../backend/tests/test_preview_layout.py) |
| frame sampling shared by preview and tagging | [`../backend/app/frame_sampling.py`](../backend/app/frame_sampling.py), [`../backend/app/tagging_service.py`](../backend/app/tagging_service.py) |
| playback modal or playback settings UI | [`../backend/app/playback_settings_service.py`](../backend/app/playback_settings_service.py), [`../backend/app/main.py`](../backend/app/main.py) |
| jobs modal filters, refresh cadence, or event display | [`../backend/app/job_service.py`](../backend/app/job_service.py), [`../backend/app/main.py`](../backend/app/main.py), [`../frontend/src/components/modals/LogViewerModal.jsx`](../frontend/src/components/modals/LogViewerModal.jsx) |
| tuning or profile-promotion behavior | [`../frontend/src/components/modals/TuneModal.jsx`](../frontend/src/components/modals/TuneModal.jsx), [`../backend/app/conversion_profile_service.py`](../backend/app/conversion_profile_service.py), [`../backend/app/job_service.py`](../backend/app/job_service.py) |
| tree badges or file status labels | [`../backend/app/library_service.py`](../backend/app/library_service.py), [`../backend/app/job_service.py`](../backend/app/job_service.py) |

## Backend Anchors

Use these only after the router above points you here.

| Path | Why you would read it |
| --- | --- |
| [`../backend/app/main.py`](../backend/app/main.py) | Stdlib HTTP entrypoint for all current frontend-facing endpoints, SSE log stream, and embedded playback responses. |
| [`../backend/app/source_service.py`](../backend/app/source_service.py) | Source validation, persistence, password preservation, reconnect, and backend-local directory browsing. |
| [`../backend/app/library_service.py`](../backend/app/library_service.py) | Tree/file metadata persistence, scans, rescans, and derived conversion/preview indicators. |
| [`../backend/app/job_service.py`](../backend/app/job_service.py) | Persistent job queue, item transitions, events, cancel/restart, and all async runtime orchestration. |
| [`../backend/app/preview_service.py`](../backend/app/preview_service.py) | Preview settings, presets, layout generation, sampling, and stored preview assets. |
| [`../backend/app/preview_layout.py`](../backend/app/preview_layout.py) | Preview layout math, aspect-ratio presets, tile ordering, and detector/image helpers that do not touch storage. |
| [`../backend/app/frame_sampling.py`](../backend/app/frame_sampling.py) | Shared interior-frame sampling helpers for preview and tagging without service-specific orchestration. |
| [`../backend/app/tagging_service.py`](../backend/app/tagging_service.py) | Closed-vocabulary tagging settings, provider calls, batch preference, and persisted tag/confidence data. |
| [`../backend/app/playback_settings_service.py`](../backend/app/playback_settings_service.py) | Playback mode persistence used by modal playback versus external open. |
| [`../backend/tests/`](../backend/tests/) | Smallest regression checks after backend-facing changes. |
