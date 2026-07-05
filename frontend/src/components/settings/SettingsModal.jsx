import SourceSettingsSection from "../../features/source/SourceSettingsSection";

function ProfilesSettingsSection({
  profileDraft,
  onUpdateProfileDraft,
  onCreateProfile,
  conversionProfiles,
  formatProfileLabel,
  isWorking
}) {
  return (
    <div className="source-settings">
      <p>Profiles stay reusable and separate from tuning runs. Tuning can promote a winning output here later.</p>
      <div className="profiles-grid">
        <div className="note-card">
          <strong>Create profile</strong>
          <div className="form-grid">
            <label>
              <span>Name</span>
              <input value={profileDraft.name} onChange={(event) => onUpdateProfileDraft("name", event.target.value)} />
            </label>
            <label>
              <span>Codec</span>
              <select value={profileDraft.video_codec} onChange={(event) => onUpdateProfileDraft("video_codec", event.target.value)}>
                <option value="h264">H.264</option>
                <option value="h265">H.265</option>
                <option value="av1">AV1</option>
              </select>
            </label>
            <label>
              <span>Max dimension</span>
              <input value={profileDraft.max_dimension} onChange={(event) => onUpdateProfileDraft("max_dimension", event.target.value)} placeholder="Optional" />
            </label>
            <label>
              <span>Quality value</span>
              <input value={profileDraft.quality_value} onChange={(event) => onUpdateProfileDraft("quality_value", event.target.value)} placeholder="20" />
            </label>
            <label className="toggle-row">
              <span>Drop audio</span>
              <input type="checkbox" checked={profileDraft.drop_audio} onChange={(event) => onUpdateProfileDraft("drop_audio", event.target.checked)} />
            </label>
            <label className="toggle-row">
              <span>Default profile</span>
              <input type="checkbox" checked={profileDraft.is_default} onChange={(event) => onUpdateProfileDraft("is_default", event.target.checked)} />
            </label>
            <label className="full-width">
              <span>Advanced encoder args</span>
              <input value={profileDraft.extra_encoder_args} onChange={(event) => onUpdateProfileDraft("extra_encoder_args", event.target.value)} placeholder="Optional ffmpeg encoder args" />
            </label>
          </div>
          <div className="inline-actions">
            <button type="button" className="primary-button" disabled={isWorking || !profileDraft.name.trim()} onClick={onCreateProfile}>
              Save profile
            </button>
          </div>
        </div>

        <div className="note-card">
          <strong>Saved profiles</strong>
          <div className="profile-list">
            {conversionProfiles.map((profile) => (
              <article key={profile.id} className="profile-row">
                <div>
                  <strong>{profile.name}</strong>
                  <p className="row-subtitle">{formatProfileLabel(profile)}</p>
                </div>
                {profile.is_default ? <span className="tree-badge">default</span> : null}
              </article>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function PreviewSettingsSection({
  previewSettings,
  onUpdatePreviewSetting,
  previewPresets,
  previewPresetName,
  onPreviewPresetNameChange,
  onLoadPreset,
  onSavePreset,
  onSavePreviewSettings,
  livePreview,
  isWorking
}) {
  return (
    <div className="source-settings">
      <p>Preview generation stays independent from conversion. Save the sampling and large-tile rules here, then use the live preview to inspect the layout before launching jobs.</p>
      <div className="form-grid">
        <label>
          <span>Sample count</span>
          <input type="number" min="3" max="24" value={previewSettings.sample_count} onChange={(event) => onUpdatePreviewSetting("sample_count", Number(event.target.value))} />
        </label>
        <label>
          <span>Large tile count</span>
          <input type="number" min="0" max="6" value={previewSettings.large_tile_count} onChange={(event) => onUpdatePreviewSetting("large_tile_count", Number(event.target.value))} />
        </label>
        <label>
          <span>Timeline flow</span>
          <select value={previewSettings.timeline_flow} onChange={(event) => onUpdatePreviewSetting("timeline_flow", event.target.value)}>
            <option value="row">Row by row</option>
            <option value="column">Column by column</option>
            <option value="shuffle">Shuffled time order</option>
          </select>
        </label>
        <label className="toggle-row">
          <span>Identity diversity</span>
          <input type="checkbox" checked={previewSettings.identity_diversity_enabled} onChange={(event) => onUpdatePreviewSetting("identity_diversity_enabled", event.target.checked)} />
        </label>
        <label className="full-width">
          <span>Saved preset</span>
          <select value={previewSettings.layout_preset_id} onChange={(event) => onUpdatePreviewSetting("layout_preset_id", event.target.value)}>
            {previewPresets.map((preset) => (
              <option key={preset.id} value={preset.id}>
                {preset.name}
              </option>
            ))}
          </select>
        </label>
        <label className="full-width">
          <span>Preset name</span>
          <input value={previewPresetName} onChange={(event) => onPreviewPresetNameChange(event.target.value)} placeholder="Balanced Grid" />
        </label>
      </div>
      <div className="inline-actions">
        <button type="button" className="ghost-button" disabled={isWorking} onClick={onLoadPreset}>
          Load preset
        </button>
        <button type="button" className="ghost-button" disabled={isWorking} onClick={() => onSavePreset("create")}>
          Save as new preset
        </button>
        <button
          type="button"
          className="ghost-button"
          disabled={isWorking || previewSettings.layout_preset_id === "default-preview-grid"}
          onClick={() => onSavePreset("update")}
        >
          Update preset
        </button>
        <button type="button" className="primary-button" disabled={isWorking} onClick={onSavePreviewSettings}>
          Save preview settings
        </button>
      </div>
      <div className="preview-settings-grid">
        <div className="note-card">
          <strong>Selection rules</strong>
          <p>First two large tiles prefer faces. Remaining large tiles prefer figures. When identity diversity is enabled, the backend falls back to separate timeline regions if a full identity pass is too expensive.</p>
        </div>
        <div className="note-card preview-layout-card">
          <strong>Live preview</strong>
          {livePreview?.image_data_url ? (
            <img className="preview-image" src={livePreview.image_data_url} alt="Live preview layout" />
          ) : (
            <div className="settings-placeholder compact-placeholder">
              <span>Generating layout preview...</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function PlaybackSettingsSection({ playbackSettings, onUpdatePlaybackSetting, onSavePlaybackSettings, isWorking }) {
  return (
    <div className="source-settings">
      <p>Playback mode is configurable because embedded viewing and external opening behave differently across machines and browser environments.</p>
      <div className="form-grid">
        <label>
          <span>Playback mode</span>
          <select value={playbackSettings.mode} onChange={(event) => onUpdatePlaybackSetting("mode", event.target.value)}>
            <option value="embedded">Embedded modal playback</option>
            <option value="external">External open</option>
          </select>
        </label>
        <label>
          <span>External strategy</span>
          <select value={playbackSettings.external_strategy} onChange={(event) => onUpdatePlaybackSetting("external_strategy", event.target.value)}>
            <option value="file_uri">File URI / link</option>
            <option value="path">Path-first</option>
          </select>
        </label>
      </div>
      <div className="inline-actions">
        <button type="button" className="primary-button" disabled={isWorking} onClick={onSavePlaybackSettings}>
          Save playback settings
        </button>
      </div>
      <div className="note-card">
        <strong>Current behavior</strong>
        <p>Embedded playback streams through the backend. External playback opens the resolved file URI when the local environment supports it.</p>
      </div>
    </div>
  );
}

function TaggingSettingsSection({ taggingSettings, onUpdateTaggingSetting, onSaveTaggingSettings, isWorking }) {
  return (
    <div className="source-settings">
      <p>Tagging stays separate from conversion and preview. The backend only stores tags selected from this allowed vocabulary plus confidence scores.</p>
      <div className="form-grid">
        <label>
          <span>Provider</span>
          <select value={taggingSettings.provider} onChange={(event) => onUpdateTaggingSetting("provider", event.target.value)}>
            <option value="openrouter">OpenRouter</option>
            <option value="gemini">Google Gemini</option>
            <option value="fal">FAL</option>
            <option value="mistral">Mistral</option>
          </select>
        </label>
        <label>
          <span>Sample count</span>
          <input type="number" min="3" max="24" value={taggingSettings.sample_count} onChange={(event) => onUpdateTaggingSetting("sample_count", Number(event.target.value))} />
        </label>
        <label className="toggle-row">
          <span>Combine frames</span>
          <input type="checkbox" checked={taggingSettings.combine_frames} onChange={(event) => onUpdateTaggingSetting("combine_frames", event.target.checked)} />
        </label>
        <label className="toggle-row">
          <span>Prefer batch</span>
          <input type="checkbox" checked={taggingSettings.prefer_batch} onChange={(event) => onUpdateTaggingSetting("prefer_batch", event.target.checked)} />
        </label>
        <label className="full-width">
          <span>Allowed vocabulary</span>
          <textarea
            rows="10"
            value={(taggingSettings.vocabulary ?? []).join("\n")}
            onChange={(event) =>
              onUpdateTaggingSetting(
                "vocabulary",
                event.target.value
                  .split("\n")
                  .map((entry) => entry.trim())
                  .filter(Boolean)
              )
            }
            placeholder="One tag per line"
          />
        </label>
      </div>
      <div className="inline-actions">
        <button type="button" className="primary-button" disabled={isWorking} onClick={onSaveTaggingSettings}>
          Save tagging settings
        </button>
      </div>
      <div className="note-card">
        <strong>Closed vocabulary only</strong>
        <p>The model can only return tags from this list. Any out-of-vocabulary labels are discarded before storage.</p>
      </div>
    </div>
  );
}

function ProviderSettingsSection({ providerSettings, onUpdateProviderSetting, onSaveProviderSettings, isWorking }) {
  return (
    <div className="source-settings">
      <p>Configure backend-only provider access here. API keys stay out of the main metadata database and are stored separately.</p>
      <div className="provider-settings-list">
        {providerSettings.map((provider) => (
          <div key={provider.provider} className="note-card">
            <div className="panel-header compact-header">
              <div>
                <strong>{provider.provider === "gemini" ? "Google Gemini" : provider.provider.toUpperCase()}</strong>
                <p className="muted">{provider.api_key_configured ? "API key stored" : "API key not stored"}</p>
              </div>
              <label className="toggle-row">
                <span>Enabled</span>
                <input type="checkbox" checked={provider.enabled} onChange={(event) => onUpdateProviderSetting(provider.provider, "enabled", event.target.checked)} />
              </label>
            </div>
            <div className="form-grid">
              <label>
                <span>Vision model</span>
                <input value={provider.vision_model} onChange={(event) => onUpdateProviderSetting(provider.provider, "vision_model", event.target.value)} />
              </label>
              <label>
                <span>Text model</span>
                <input value={provider.text_model} onChange={(event) => onUpdateProviderSetting(provider.provider, "text_model", event.target.value)} placeholder="Optional" />
              </label>
              <label>
                <span>API key</span>
                <input
                  type="password"
                  value={provider.api_key}
                  onChange={(event) => onUpdateProviderSetting(provider.provider, "api_key", event.target.value)}
                  placeholder={provider.api_key_configured ? "Leave blank to keep stored key" : ""}
                />
              </label>
              <label className="toggle-row">
                <span>Prefer batch</span>
                <input type="checkbox" checked={provider.prefer_batch} onChange={(event) => onUpdateProviderSetting(provider.provider, "prefer_batch", event.target.checked)} />
              </label>
            </div>
          </div>
        ))}
      </div>
      <div className="inline-actions">
        <button type="button" className="primary-button" disabled={isWorking} onClick={onSaveProviderSettings}>
          Save provider settings
        </button>
      </div>
    </div>
  );
}

function renderSettingsDetail(props) {
  const { selectedSettingsSection } = props;

  if (selectedSettingsSection === "source") {
    return (
      <SourceSettingsSection
        source={props.source}
        sourceForm={props.sourceForm}
        sourceFormIsLocal={props.sourceFormIsLocal}
        isWorking={props.isWorking}
        localDirectoryBrowser={props.localDirectoryBrowser}
        isLocalDirectoryBrowserOpen={props.isLocalDirectoryBrowserOpen}
        testResult={props.testResult}
        onUpdateSourceField={props.onUpdateSourceField}
        onLoadLocalDirectoryBrowser={props.onLoadLocalDirectoryBrowser}
        onSelectLocalDirectory={props.onSelectLocalDirectory}
        onSourceTest={props.onSourceTest}
        onReconnect={props.onReconnect}
        onScanSource={props.onScanSource}
        onSourceSave={props.onSourceSave}
      />
    );
  }

  if (selectedSettingsSection === "profiles") {
    return (
      <ProfilesSettingsSection
        profileDraft={props.profileDraft}
        onUpdateProfileDraft={props.onUpdateProfileDraft}
        onCreateProfile={props.onCreateProfile}
        conversionProfiles={props.conversionProfiles}
        formatProfileLabel={props.formatProfileLabel}
        isWorking={props.isWorking}
      />
    );
  }

  if (selectedSettingsSection === "preview") {
    return (
      <PreviewSettingsSection
        previewSettings={props.previewSettings}
        onUpdatePreviewSetting={props.onUpdatePreviewSetting}
        previewPresets={props.previewPresets}
        previewPresetName={props.previewPresetName}
        onPreviewPresetNameChange={props.onPreviewPresetNameChange}
        onLoadPreset={props.onLoadPreset}
        onSavePreset={props.onSavePreset}
        onSavePreviewSettings={props.onSavePreviewSettings}
        livePreview={props.livePreview}
        isWorking={props.isWorking}
      />
    );
  }

  if (selectedSettingsSection === "playback") {
    return (
      <PlaybackSettingsSection
        playbackSettings={props.playbackSettings}
        onUpdatePlaybackSetting={props.onUpdatePlaybackSetting}
        onSavePlaybackSettings={props.onSavePlaybackSettings}
        isWorking={props.isWorking}
      />
    );
  }

  if (selectedSettingsSection === "tagging") {
    return (
      <TaggingSettingsSection
        taggingSettings={props.taggingSettings}
        onUpdateTaggingSetting={props.onUpdateTaggingSetting}
        onSaveTaggingSettings={props.onSaveTaggingSettings}
        isWorking={props.isWorking}
      />
    );
  }

  if (selectedSettingsSection === "providers") {
    return (
      <ProviderSettingsSection
        providerSettings={props.providerSettings}
        onUpdateProviderSetting={props.onUpdateProviderSetting}
        onSaveProviderSettings={props.onSaveProviderSettings}
        isWorking={props.isWorking}
      />
    );
  }

  return (
    <div className="settings-placeholder">
      <span>This section remains a secondary maintenance flow and stays out of the main library view.</span>
    </div>
  );
}

export default function SettingsModal(props) {
  const { isOpen, onClose, settingsSections, selectedSettingsSection, onSelectSection } = props;

  if (!isOpen) {
    return null;
  }

  const selectedSectionLabel =
    settingsSections.find((section) => section.id === selectedSettingsSection)?.label ?? "Settings";

  return (
    <div className="overlay-backdrop" onClick={onClose}>
      <section className="overlay panel modal-shell settings-shell" onClick={(event) => event.stopPropagation()}>
        <div className="panel-header">
          <div>
            <p className="section-kicker">Settings</p>
            <h2>{selectedSectionLabel}</h2>
          </div>
          <button type="button" className="ghost-button" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="settings-layout">
          <nav className="settings-nav">
            {settingsSections.map((section) => (
              <button
                key={section.id}
                type="button"
                className={`settings-link ${selectedSettingsSection === section.id ? "active" : ""}`}
                onClick={() => onSelectSection(section.id)}
              >
                {section.label}
              </button>
            ))}
          </nav>
          <section className="settings-detail">
            <h3>{selectedSectionLabel}</h3>
            {renderSettingsDetail(props)}
          </section>
        </div>
      </section>
    </div>
  );
}
