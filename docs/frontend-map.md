# Frontend Map

The frontend keeps [`../frontend/src/App.jsx`](../frontend/src/App.jsx) as the orchestration shell and pushes most UI edit work into smaller components. Use this page when you already know the task is frontend-only and want the smallest file to open first.

| Task | Primary file | Also check |
| --- | --- | --- |
| Top bar, queue summary, settings/logs/jobs buttons | [`../frontend/src/components/layout/AppHeader.jsx`](../frontend/src/components/layout/AppHeader.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) |
| Directory tree rows and subtree indicators | [`../frontend/src/components/layout/DirectoryTreePanel.jsx`](../frontend/src/components/layout/DirectoryTreePanel.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) |
| File table rows and folder-level action buttons | [`../frontend/src/components/layout/FileBrowserPanel.jsx`](../frontend/src/components/layout/FileBrowserPanel.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) |
| Right-side preview summary panel | [`../frontend/src/components/layout/LibraryPreviewPanel.jsx`](../frontend/src/components/layout/LibraryPreviewPanel.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) |
| Source settings fields, local-folder browser, save/test/reconnect UI | [`../frontend/src/features/source/SourceSettingsSection.jsx`](../frontend/src/features/source/SourceSettingsSection.jsx) | [`../frontend/src/features/source/sourceHelpers.js`](../frontend/src/features/source/sourceHelpers.js), [`../frontend/src/api.js`](../frontend/src/api.js) |
| RU/EN copy, settings-section labels, and visual-mode strings | [`../frontend/src/i18n.js`](../frontend/src/i18n.js) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx), [`../frontend/src/components/layout/AppHeader.jsx`](../frontend/src/components/layout/AppHeader.jsx) |
| Source form defaults, source payload shaping, local-vs-remote helpers | [`../frontend/src/features/source/sourceHelpers.js`](../frontend/src/features/source/sourceHelpers.js) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) |
| Source API calls and frontend/backend request payloads | [`../frontend/src/api.js`](../frontend/src/api.js) | [`../backend/app/main.py`](../backend/app/main.py), [`../backend/app/source_service.py`](../backend/app/source_service.py) |
| Jobs modal UI | [`../frontend/src/components/modals/JobsModal.jsx`](../frontend/src/components/modals/JobsModal.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) |
| Log viewer modal UI and preset filter fields | [`../frontend/src/components/modals/LogViewerModal.jsx`](../frontend/src/components/modals/LogViewerModal.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) |
| File details modal UI | [`../frontend/src/components/modals/FileDetailsModal.jsx`](../frontend/src/components/modals/FileDetailsModal.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) |
| Tune modal UI and tuning-result promotion entry point | [`../frontend/src/components/modals/TuneModal.jsx`](../frontend/src/components/modals/TuneModal.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) |
| Preview, playback, tagging, provider, and profile settings sections | [`../frontend/src/components/settings/SettingsModal.jsx`](../frontend/src/components/settings/SettingsModal.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx), [`../frontend/src/api.js`](../frontend/src/api.js) |
| Shared frontend styling for shell and extracted modals | [`../frontend/src/styles.css`](../frontend/src/styles.css) | None |

Common small-change entry points:

- Header / tree / file list / preview panel: [`../frontend/src/components/layout/`](../frontend/src/components/layout/)
- Source settings UI copy/fields: [`../frontend/src/features/source/SourceSettingsSection.jsx`](../frontend/src/features/source/SourceSettingsSection.jsx)
- Source payload/API mismatch: [`../frontend/src/features/source/sourceHelpers.js`](../frontend/src/features/source/sourceHelpers.js), [`../frontend/src/api.js`](../frontend/src/api.js)
- Jobs/detail/tune modal tweaks: [`../frontend/src/components/modals/`](../frontend/src/components/modals/)
- Preview/tagging/playback settings forms: [`../frontend/src/components/settings/SettingsModal.jsx`](../frontend/src/components/settings/SettingsModal.jsx)
- Cross-modal flow questions: [`frontend-flows.md`](frontend-flows.md)
