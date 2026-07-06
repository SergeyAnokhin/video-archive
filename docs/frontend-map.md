# Frontend Map

The frontend keeps [`../frontend/src/App.jsx`](../frontend/src/App.jsx) as the orchestration shell and pushes most UI edit work into smaller components. Use this page when you already know the task is frontend-only and want the smallest file to open first.

| Task | Primary file | Also check |
| --- | --- | --- |
| Top bar, queue summary, settings/logs/jobs buttons | [`../frontend/src/components/layout/AppHeader.jsx`](../frontend/src/components/layout/AppHeader.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) |
| App-wide date/size/status/profile formatting helpers | [`../frontend/src/appFormatters.js`](../frontend/src/appFormatters.js) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx), the consuming component in [`../frontend/src/components/`](../frontend/src/components/) |
| Settings section ids and visual-mode sequence | [`../frontend/src/appShellConfig.js`](../frontend/src/appShellConfig.js) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx), [`../frontend/src/components/layout/AppHeader.jsx`](../frontend/src/components/layout/AppHeader.jsx) |
| Directory tree rows and subtree indicators | [`../frontend/src/components/layout/DirectoryTreePanel.jsx`](../frontend/src/components/layout/DirectoryTreePanel.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) |
| File table rows and folder-level action buttons | [`../frontend/src/components/layout/FileBrowserPanel.jsx`](../frontend/src/components/layout/FileBrowserPanel.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) |
| Right-side preview summary panel | [`../frontend/src/components/layout/LibraryPreviewPanel.jsx`](../frontend/src/components/layout/LibraryPreviewPanel.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) |
| Source settings fields, local-folder browser, save/test/reconnect UI | [`../frontend/src/features/source/SourceSettingsSection.jsx`](../frontend/src/features/source/SourceSettingsSection.jsx) | [`../frontend/src/features/source/sourceHelpers.js`](../frontend/src/features/source/sourceHelpers.js), [`../frontend/src/api.js`](../frontend/src/api.js) |
| RU/EN copy and translation keys | [`../frontend/src/i18n.js`](../frontend/src/i18n.js) | Use `rg "namespace\\." ../frontend/src/i18n.js` to jump to one message block before opening components. |
| Source form defaults, source payload shaping, local-vs-remote helpers | [`../frontend/src/features/source/sourceHelpers.js`](../frontend/src/features/source/sourceHelpers.js) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) |
| Source API calls and frontend/backend request payloads | [`../frontend/src/api.js`](../frontend/src/api.js) | [`../backend/app/main.py`](../backend/app/main.py), [`../backend/app/source_service.py`](../backend/app/source_service.py) |
| Jobs modal UI | [`../frontend/src/components/modals/JobsModal.jsx`](../frontend/src/components/modals/JobsModal.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) |
| Log viewer modal UI and preset filter fields | [`../frontend/src/components/modals/LogViewerModal.jsx`](../frontend/src/components/modals/LogViewerModal.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) |
| Embedded playback modal | [`../frontend/src/components/modals/PlaybackModal.jsx`](../frontend/src/components/modals/PlaybackModal.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx), [`../backend/app/playback_settings_service.py`](../backend/app/playback_settings_service.py) |
| Conversion confirmation modal | [`../frontend/src/components/modals/ConversionModal.jsx`](../frontend/src/components/modals/ConversionModal.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx), [`../backend/app/conversion_profile_service.py`](../backend/app/conversion_profile_service.py) |
| Tuning-promotion modal | [`../frontend/src/components/modals/PromotionModal.jsx`](../frontend/src/components/modals/PromotionModal.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx), [`../backend/app/conversion_profile_service.py`](../backend/app/conversion_profile_service.py) |
| File details modal UI | [`../frontend/src/components/modals/FileDetailsModal.jsx`](../frontend/src/components/modals/FileDetailsModal.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) |
| Tune modal UI and tuning-result promotion entry point | [`../frontend/src/components/modals/TuneModal.jsx`](../frontend/src/components/modals/TuneModal.jsx) | [`../frontend/src/App.jsx`](../frontend/src/App.jsx) |
| Preview, playback, tagging, provider, and profile settings shell | [`../frontend/src/components/settings/SettingsModal.jsx`](../frontend/src/components/settings/SettingsModal.jsx) | [`../frontend/src/components/settings/SettingsSections.jsx`](../frontend/src/components/settings/SettingsSections.jsx) |
| Settings section form bodies | [`../frontend/src/components/settings/SettingsSections.jsx`](../frontend/src/components/settings/SettingsSections.jsx) | [`../frontend/src/api.js`](../frontend/src/api.js), [`../backend/app/main.py`](../backend/app/main.py) |
| Visual-mode tokens and background gradients | [`../frontend/src/styles/theme.css`](../frontend/src/styles/theme.css) | [`../frontend/src/styles.css`](../frontend/src/styles.css) for token consumers |
| Shared frontend styling for shell, lists, modals, and responsive layout | [`../frontend/src/styles.css`](../frontend/src/styles.css) | Start from the selector block you grep, not the full file. |

Common small-change entry points:

- Header / tree / file list / preview panel: [`../frontend/src/components/layout/`](../frontend/src/components/layout/)
- Source settings UI copy/fields: [`../frontend/src/features/source/SourceSettingsSection.jsx`](../frontend/src/features/source/SourceSettingsSection.jsx)
- Source payload/API mismatch: [`../frontend/src/features/source/sourceHelpers.js`](../frontend/src/features/source/sourceHelpers.js), [`../frontend/src/api.js`](../frontend/src/api.js)
- Jobs/detail/tune modal tweaks: [`../frontend/src/components/modals/`](../frontend/src/components/modals/)
- Preview/tagging/playback settings forms: [`../frontend/src/components/settings/SettingsSections.jsx`](../frontend/src/components/settings/SettingsSections.jsx)
- Theme-only work: [`../frontend/src/styles/theme.css`](../frontend/src/styles/theme.css)
- Cross-modal flow questions: [`frontend-flows.md`](frontend-flows.md)
