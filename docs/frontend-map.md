# Frontend Map

The frontend now keeps `frontend/src/App.jsx` as the shell/orchestration file and moves the most expensive modal and source-settings surfaces into smaller edit points. Use this map to jump straight to the smallest file that matches the task.

| Task | Primary file | Also check |
| --- | --- | --- |
| Source settings fields, local-folder browser, save/test/reconnect UI | [`../frontend/src/features/source/SourceSettingsSection.jsx`](../frontend/src/features/source/SourceSettingsSection.jsx) | [`../frontend/src/features/source/sourceHelpers.js`](../frontend/src/features/source/sourceHelpers.js), [`../frontend/src/api.js`](../frontend/src/api.js) |
| Source form defaults, source payload shaping, local-vs-remote helpers | [`../frontend/src/features/source/sourceHelpers.js`](../frontend/src/features/source/sourceHelpers.js) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) |
| Source API calls and frontend/backend request payloads | [`../frontend/src/api.js`](../frontend/src/api.js) | [`../backend/app/main.py`](../backend/app/main.py), [`../backend/app/source_service.py`](../backend/app/source_service.py) |
| Jobs modal UI | [`../frontend/src/components/modals/JobsModal.jsx`](../frontend/src/components/modals/JobsModal.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) |
| File details modal UI | [`../frontend/src/components/modals/FileDetailsModal.jsx`](../frontend/src/components/modals/FileDetailsModal.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) |
| Tune modal UI and tuning-result promotion entry point | [`../frontend/src/components/modals/TuneModal.jsx`](../frontend/src/components/modals/TuneModal.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) |
| Preview, playback, tagging, provider, and profile settings sections | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) | [`../frontend/src/api.js`](../frontend/src/api.js) |
| Shared frontend styling for shell and extracted modals | [`../frontend/src/styles.css`](../frontend/src/styles.css) | None |

Common small-change entry points:

- Source settings UI copy/fields: [`../frontend/src/features/source/SourceSettingsSection.jsx`](../frontend/src/features/source/SourceSettingsSection.jsx)
- Source payload/API mismatch: [`../frontend/src/features/source/sourceHelpers.js`](../frontend/src/features/source/sourceHelpers.js), [`../frontend/src/api.js`](../frontend/src/api.js)
- Jobs/detail/tune modal tweaks: [`../frontend/src/components/modals/`](../frontend/src/components/modals/)
- Preview/tagging/playback settings forms: [`../frontend/src/App.jsx`](../frontend/src/App.jsx)
