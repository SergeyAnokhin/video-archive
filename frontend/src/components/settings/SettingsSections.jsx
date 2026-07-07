import { ArrowDown, ArrowUp, Download, Play, Plus, RefreshCw, Save, ShieldCheck, Trash2, Upload } from "lucide-react";
import SourceSettingsSection from "../../features/source/SourceSettingsSection";

function ProfilesSettingsSection({
  profileDraft,
  onUpdateProfileDraft,
  onCreateProfile,
  conversionProfiles,
  formatProfileLabel,
  isWorking,
  t
}) {
  return (
    <div className="source-settings">
      <p>{t("profiles.intro")}</p>
      <div className="profiles-grid">
        <div className="note-card">
          <strong>{t("profiles.create")}</strong>
          <div className="form-grid">
            <label>
              <span>{t("profiles.name")}</span>
              <input value={profileDraft.name} onChange={(event) => onUpdateProfileDraft("name", event.target.value)} />
            </label>
            <label>
              <span>{t("profiles.codec")}</span>
              <select value={profileDraft.video_codec} onChange={(event) => onUpdateProfileDraft("video_codec", event.target.value)}>
                <option value="h264">H.264</option>
                <option value="h265">H.265</option>
                <option value="av1">AV1</option>
              </select>
            </label>
            <label>
              <span>{t("profiles.maxDimension")}</span>
              <input value={profileDraft.max_dimension} onChange={(event) => onUpdateProfileDraft("max_dimension", event.target.value)} placeholder={t("profiles.optional")} />
            </label>
            <label>
              <span>{t("profiles.qualityValue")}</span>
              <input value={profileDraft.quality_value} onChange={(event) => onUpdateProfileDraft("quality_value", event.target.value)} placeholder="20" />
            </label>
            <label className="toggle-row">
              <span>{t("profiles.dropAudio")}</span>
              <input type="checkbox" checked={profileDraft.drop_audio} onChange={(event) => onUpdateProfileDraft("drop_audio", event.target.checked)} />
            </label>
            <label className="toggle-row">
              <span>{t("profiles.defaultProfile")}</span>
              <input type="checkbox" checked={profileDraft.is_default} onChange={(event) => onUpdateProfileDraft("is_default", event.target.checked)} />
            </label>
            <label className="full-width">
              <span>{t("profiles.advancedArgs")}</span>
              <input value={profileDraft.extra_encoder_args} onChange={(event) => onUpdateProfileDraft("extra_encoder_args", event.target.value)} placeholder={t("profiles.advancedPlaceholder")} />
            </label>
          </div>
          <div className="inline-actions">
            <button type="button" className="primary-button icon-button" disabled={isWorking || !profileDraft.name.trim()} onClick={onCreateProfile}>
              <Save size={16} />
              <span>{t("profiles.saveProfile")}</span>
            </button>
          </div>
        </div>

        <div className="note-card">
          <strong>{t("profiles.saved")}</strong>
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
  isWorking,
  t
}) {
  return (
    <div className="source-settings">
      <p>{t("previewSettings.intro")}</p>
      <div className="form-grid">
        <label>
          <span>{t("previewSettings.sampleCount")}</span>
          <input type="number" min="3" max="24" value={previewSettings.sample_count} onChange={(event) => onUpdatePreviewSetting("sample_count", Number(event.target.value))} />
        </label>
        <label>
          <span>{t("previewSettings.largeTileCount")}</span>
          <input type="number" min="0" max="6" value={previewSettings.large_tile_count} onChange={(event) => onUpdatePreviewSetting("large_tile_count", Number(event.target.value))} />
        </label>
        <label>
          <span>{t("previewSettings.timelineFlow")}</span>
          <select value={previewSettings.timeline_flow} onChange={(event) => onUpdatePreviewSetting("timeline_flow", event.target.value)}>
            <option value="row">{t("previewSettings.row")}</option>
            <option value="column">{t("previewSettings.column")}</option>
            <option value="shuffle">{t("previewSettings.shuffle")}</option>
          </select>
        </label>
        <label className="toggle-row">
          <span>{t("previewSettings.identityDiversity")}</span>
          <input type="checkbox" checked={previewSettings.identity_diversity_enabled} onChange={(event) => onUpdatePreviewSetting("identity_diversity_enabled", event.target.checked)} />
        </label>
        <label className="full-width">
          <span>{t("previewSettings.savedPreset")}</span>
          <select value={previewSettings.layout_preset_id} onChange={(event) => onUpdatePreviewSetting("layout_preset_id", event.target.value)}>
            {previewPresets.map((preset) => (
              <option key={preset.id} value={preset.id}>
                {preset.name}
              </option>
            ))}
          </select>
        </label>
        <label className="full-width">
          <span>{t("previewSettings.presetName")}</span>
          <input value={previewPresetName} onChange={(event) => onPreviewPresetNameChange(event.target.value)} placeholder="Balanced Grid" />
        </label>
      </div>
      <div className="inline-actions">
        <button type="button" className="ghost-button icon-button" disabled={isWorking} onClick={onLoadPreset}>
          <Download size={16} />
          <span>{t("previewSettings.loadPreset")}</span>
        </button>
        <button type="button" className="ghost-button icon-button" disabled={isWorking} onClick={() => onSavePreset("create")}>
          <Save size={16} />
          <span>{t("previewSettings.savePreset")}</span>
        </button>
        <button
          type="button"
          className="ghost-button icon-button"
          disabled={isWorking || previewSettings.layout_preset_id === "default-preview-grid"}
          onClick={() => onSavePreset("update")}
        >
          <Upload size={16} />
          <span>{t("previewSettings.updatePreset")}</span>
        </button>
        <button type="button" className="primary-button icon-button" disabled={isWorking} onClick={onSavePreviewSettings}>
          <Save size={16} />
          <span>{t("previewSettings.saveSettings")}</span>
        </button>
      </div>
      <div className="preview-settings-grid">
        <div className="note-card">
          <strong>{t("previewSettings.rulesTitle")}</strong>
          <p>{t("previewSettings.rulesBody")}</p>
          <p>{t("previewSettings.fixedAspectRatio")}</p>
        </div>
        <div className="note-card preview-layout-card">
          <strong>{t("previewSettings.livePreview")}</strong>
          {livePreview?.image_data_url ? (
            <img className="preview-image" src={livePreview.image_data_url} alt="Live preview layout" />
          ) : (
            <div className="settings-placeholder compact-placeholder">
              <span>{t("previewSettings.generating")}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function PlaybackSettingsSection({ playbackSettings, onUpdatePlaybackSetting, onSavePlaybackSettings, isWorking, t }) {
  return (
    <div className="source-settings">
      <p>{t("playbackSettings.intro")}</p>
      <div className="form-grid">
        <label>
          <span>{t("playbackSettings.mode")}</span>
          <select value={playbackSettings.mode} onChange={(event) => onUpdatePlaybackSetting("mode", event.target.value)}>
            <option value="embedded">{t("playbackSettings.embedded")}</option>
            <option value="external">{t("playbackSettings.external")}</option>
          </select>
        </label>
        <label>
          <span>{t("playbackSettings.strategy")}</span>
          <select value={playbackSettings.external_strategy} onChange={(event) => onUpdatePlaybackSetting("external_strategy", event.target.value)}>
            <option value="file_uri">{t("playbackSettings.fileUri")}</option>
            <option value="path">{t("playbackSettings.path")}</option>
          </select>
        </label>
      </div>
      <div className="inline-actions">
        <button type="button" className="primary-button icon-button" disabled={isWorking} onClick={onSavePlaybackSettings}>
          <Play size={16} />
          <span>{t("playbackSettings.save")}</span>
        </button>
      </div>
      <div className="note-card">
        <strong>{t("playbackSettings.current")}</strong>
        <p>{t("playbackSettings.currentBody")}</p>
      </div>
    </div>
  );
}

function TaggingSettingsSection({ taggingSettings, taggingProviderOptions, onUpdateTaggingSetting, onSaveTaggingSettings, isWorking, t }) {
  return (
    <div className="source-settings">
      <p>{t("taggingSettings.intro")}</p>
      <div className="form-grid">
        <label>
          <span>{t("taggingSettings.provider")}</span>
          <select value={taggingSettings.provider_id} onChange={(event) => onUpdateTaggingSetting("provider_id", event.target.value)}>
            {taggingProviderOptions.length ? (
              taggingProviderOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))
            ) : (
              <option value="">{t("taggingSettings.noProviders")}</option>
            )}
          </select>
        </label>
        <label>
          <span>{t("taggingSettings.sampleCount")}</span>
          <input type="number" min="3" max="24" value={taggingSettings.sample_count} onChange={(event) => onUpdateTaggingSetting("sample_count", Number(event.target.value))} />
        </label>
        <label className="toggle-row">
          <span>{t("taggingSettings.combine")}</span>
          <input type="checkbox" checked={taggingSettings.combine_frames} onChange={(event) => onUpdateTaggingSetting("combine_frames", event.target.checked)} />
        </label>
        <label className="toggle-row">
          <span>{t("taggingSettings.preferBatch")}</span>
          <input type="checkbox" checked={taggingSettings.prefer_batch} onChange={(event) => onUpdateTaggingSetting("prefer_batch", event.target.checked)} />
        </label>
        <label className="full-width">
          <span>{t("taggingSettings.vocabulary")}</span>
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
            placeholder={t("taggingSettings.vocabularyPlaceholder")}
          />
        </label>
      </div>
      <div className="inline-actions">
        <button type="button" className="primary-button icon-button" disabled={isWorking} onClick={onSaveTaggingSettings}>
          <Save size={16} />
          <span>{t("taggingSettings.save")}</span>
        </button>
      </div>
      <div className="note-card">
        <strong>{t("taggingSettings.closedTitle")}</strong>
        <p>{t("taggingSettings.closedBody")}</p>
      </div>
    </div>
  );
}

function ProviderSettingsSection({
  providerSettings,
  onAddProviderSetting,
  onUpdateProviderSetting,
  onMoveProviderSetting,
  onRemoveProviderSetting,
  onLoadProviderModels,
  onSaveProviderSettings,
  isWorking,
  t
}) {
  return (
    <div className="source-settings">
      <p>{t("providerSettings.intro")}</p>
      <div className="provider-settings-list">
        {providerSettings.map((provider) => (
          <div key={provider.id} className="note-card provider-entry-card">
            <div className="panel-header compact-header">
              <div className="provider-entry-heading">
                <strong>{provider.label || t("providerSettings.unnamed")}</strong>
                <p className="muted">{t(`providerSettings.providerNames.${provider.provider}`)}</p>
                <p className="muted">{provider.api_key_configured ? t("providerSettings.keyStored") : t("providerSettings.keyMissing")}</p>
              </div>
              <div className="provider-entry-actions">
                <button type="button" className="ghost-button icon-button" onClick={() => onMoveProviderSetting(provider.id, "up")} disabled={isWorking || provider.order_index === 0}>
                  <ArrowUp size={16} />
                  <span>{t("providerSettings.moveUp")}</span>
                </button>
                <button type="button" className="ghost-button icon-button" onClick={() => onMoveProviderSetting(provider.id, "down")} disabled={isWorking || provider.order_index === providerSettings.length - 1}>
                  <ArrowDown size={16} />
                  <span>{t("providerSettings.moveDown")}</span>
                </button>
                <button type="button" className="ghost-button icon-button" onClick={() => onRemoveProviderSetting(provider.id)} disabled={isWorking}>
                  <Trash2 size={16} />
                  <span>{t("providerSettings.remove")}</span>
                </button>
              </div>
            </div>
            <div className="form-grid">
              <label>
                <span>{t("providerSettings.providerType")}</span>
                <select value={provider.provider} onChange={(event) => onUpdateProviderSetting(provider.id, "provider", event.target.value)}>
                  <option value="openrouter">OpenRouter</option>
                  <option value="gemini">Google Gemini</option>
                  <option value="fal">FAL</option>
                  <option value="mistral">Mistral</option>
                </select>
              </label>
              <label>
                <span>{t("providerSettings.entryName")}</span>
                <input value={provider.label} onChange={(event) => onUpdateProviderSetting(provider.id, "label", event.target.value)} placeholder={t("providerSettings.entryPlaceholder")} />
              </label>
              <label>
                <span>{t("providerSettings.visionModel")}</span>
                <input list={`provider-models-${provider.id}`} value={provider.vision_model} onChange={(event) => onUpdateProviderSetting(provider.id, "vision_model", event.target.value)} />
                <datalist id={`provider-models-${provider.id}`}>
                  {(provider.available_models ?? []).map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.label}
                    </option>
                  ))}
                </datalist>
              </label>
              <label>
                <span>{t("providerSettings.textModel")}</span>
                <input value={provider.text_model} onChange={(event) => onUpdateProviderSetting(provider.id, "text_model", event.target.value)} placeholder={t("providerSettings.textPlaceholder")} />
              </label>
              <label>
                <span>{t("providerSettings.apiKey")}</span>
                <input
                  type="password"
                  value={provider.api_key}
                  onChange={(event) => onUpdateProviderSetting(provider.id, "api_key", event.target.value)}
                  placeholder={provider.api_key_configured ? "Leave blank to keep stored key" : ""}
                />
              </label>
              <label className="toggle-row">
                <span>{t("providerSettings.preferBatch")}</span>
                <input type="checkbox" checked={provider.prefer_batch} onChange={(event) => onUpdateProviderSetting(provider.id, "prefer_batch", event.target.checked)} />
              </label>
              <label className="toggle-row">
                <span>{t("providerSettings.enabled")}</span>
                <input type="checkbox" checked={provider.enabled} onChange={(event) => onUpdateProviderSetting(provider.id, "enabled", event.target.checked)} />
              </label>
            </div>
            <div className="inline-actions">
              <button type="button" className="ghost-button icon-button" disabled={isWorking || provider.is_loading_models} onClick={() => onLoadProviderModels(provider.id)}>
                <RefreshCw size={16} />
                <span>{provider.is_loading_models ? t("providerSettings.loadingModels") : t("providerSettings.loadModels")}</span>
              </button>
            </div>
          </div>
        ))}
      </div>
      <div className="inline-actions">
        <button type="button" className="ghost-button icon-button" disabled={isWorking} onClick={onAddProviderSetting}>
          <Plus size={16} />
          <span>{t("providerSettings.add")}</span>
        </button>
        <button type="button" className="primary-button icon-button" disabled={isWorking} onClick={onSaveProviderSettings}>
          <ShieldCheck size={16} />
          <span>{t("providerSettings.save")}</span>
        </button>
      </div>
    </div>
  );
}

export function renderSettingsDetail(props) {
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
        t={props.t}
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
        t={props.t}
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
        t={props.t}
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
        t={props.t}
      />
    );
  }

  if (selectedSettingsSection === "tagging") {
    return (
      <TaggingSettingsSection
        taggingSettings={props.taggingSettings}
        taggingProviderOptions={props.taggingProviderOptions}
        onUpdateTaggingSetting={props.onUpdateTaggingSetting}
        onSaveTaggingSettings={props.onSaveTaggingSettings}
        isWorking={props.isWorking}
        t={props.t}
      />
    );
  }

  if (selectedSettingsSection === "providers") {
    return (
      <ProviderSettingsSection
        providerSettings={props.providerSettings}
        onAddProviderSetting={props.onAddProviderSetting}
        onUpdateProviderSetting={props.onUpdateProviderSetting}
        onMoveProviderSetting={props.onMoveProviderSetting}
        onRemoveProviderSetting={props.onRemoveProviderSetting}
        onLoadProviderModels={props.onLoadProviderModels}
        onSaveProviderSettings={props.onSaveProviderSettings}
        isWorking={props.isWorking}
        t={props.t}
      />
    );
  }

  return (
    <div className="settings-placeholder">
      <span>{props.t("settings.secondaryFlow")}</span>
    </div>
  );
}
