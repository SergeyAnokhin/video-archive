import { Eye, Play, Save, X } from "lucide-react";

export default function TuneModal({
  isOpen,
  selectedFile,
  tuneDraft,
  tuningJob,
  tuningVariants,
  tuningEvents,
  isWorking,
  onClose,
  onUpdateTuneDraft,
  onUpdateTuneParameter,
  onUpdateTuneCodec,
  onRunTune,
  onOpenVariantFile,
  onPromoteVariant,
  formatDate,
  t
}) {
  if (!isOpen) {
    return null;
  }

  return (
    <div className="overlay-backdrop" onClick={onClose}>
      <section className="overlay panel modal-shell tuning-shell" onClick={(event) => event.stopPropagation()}>
        <div className="panel-header">
          <div>
            <p className="section-kicker">{t("tune.kicker")}</p>
            <h2>{selectedFile?.file_name ?? t("details.titleFallback")}</h2>
          </div>
          <button type="button" className="ghost-button icon-button" onClick={onClose}>
            <X size={16} />
            <span>{t("tune.back")}</span>
          </button>
        </div>

        <div className="tuning-grid">
          <div className="tuning-config">
            <p>{t("tune.intro")}</p>
            <div className="tuning-axis-grid">
              <button
                type="button"
                className={`tuning-axis-card${tuneDraft.parameter === "dimension" ? " active" : ""}`}
                onClick={() => onUpdateTuneParameter("dimension")}
              >
                <strong>{t("tune.dimensionAxis")}</strong>
                <span>{t("tune.dimensionAxisHint")}</span>
              </button>
              <button
                type="button"
                className={`tuning-axis-card${tuneDraft.parameter === "quality" ? " active" : ""}`}
                onClick={() => onUpdateTuneParameter("quality")}
              >
                <strong>{t("tune.qualityAxis")}</strong>
                <span>{t("tune.qualityAxisHint")}</span>
              </button>
              <button
                type="button"
                className={`tuning-axis-card${tuneDraft.parameter === "codec" ? " active" : ""}`}
                onClick={() => onUpdateTuneParameter("codec")}
              >
                <strong>{t("tune.codecAxis")}</strong>
                <span>{t("tune.codecAxisHint")}</span>
              </button>
            </div>

            <div className="form-grid">
              {tuneDraft.parameter === "dimension" ? (
                <label className="full-width">
                  <span>{t("tune.dimensionAxis")}</span>
                  <div className="compact-number-row">
                    <label className="compact-field">
                      <span>{t("tune.rangeFrom")}</span>
                      <input
                        className="tuning-number-input"
                        value={tuneDraft.dimensionMin}
                        onChange={(event) => onUpdateTuneDraft("dimensionMin", event.target.value)}
                        inputMode="numeric"
                      />
                    </label>
                    <label className="compact-field">
                      <span>{t("tune.rangeTo")}</span>
                      <input
                        className="tuning-number-input"
                        value={tuneDraft.dimensionMax}
                        onChange={(event) => onUpdateTuneDraft("dimensionMax", event.target.value)}
                        inputMode="numeric"
                      />
                    </label>
                    <label className="compact-field">
                      <span>{t("tune.rangeStep")}</span>
                      <input
                        className="tuning-number-input"
                        value={tuneDraft.dimensionStep}
                        onChange={(event) => onUpdateTuneDraft("dimensionStep", event.target.value)}
                        inputMode="numeric"
                      />
                    </label>
                  </div>
                </label>
              ) : null}

              {tuneDraft.parameter === "quality" ? (
                <label className="full-width">
                  <span>{t("tune.qualityAxis")}</span>
                  <div className="compact-number-row">
                    <label className="compact-field">
                      <span>{t("tune.rangeFrom")}</span>
                      <input
                        className="tuning-number-input"
                        value={tuneDraft.qualityMin}
                        onChange={(event) => onUpdateTuneDraft("qualityMin", event.target.value)}
                        inputMode="numeric"
                      />
                    </label>
                    <label className="compact-field">
                      <span>{t("tune.rangeTo")}</span>
                      <input
                        className="tuning-number-input"
                        value={tuneDraft.qualityMax}
                        onChange={(event) => onUpdateTuneDraft("qualityMax", event.target.value)}
                        inputMode="numeric"
                      />
                    </label>
                    <label className="compact-field">
                      <span>{t("tune.rangeStep")}</span>
                      <input
                        className="tuning-number-input"
                        value={tuneDraft.qualityStep}
                        onChange={(event) => onUpdateTuneDraft("qualityStep", event.target.value)}
                        inputMode="numeric"
                      />
                    </label>
                  </div>
                </label>
              ) : null}

              {tuneDraft.parameter === "codec" ? (
                <label className="full-width">
                  <span>{t("tune.codecs")}</span>
                  <div className="checkbox-grid">
                    <label className="toggle-chip">
                      <input type="checkbox" checked={tuneDraft.codecs.h264} onChange={(event) => onUpdateTuneCodec("h264", event.target.checked)} />
                      <span>H.264</span>
                    </label>
                    <label className="toggle-chip">
                      <input type="checkbox" checked={tuneDraft.codecs.h265} onChange={(event) => onUpdateTuneCodec("h265", event.target.checked)} />
                      <span>H.265</span>
                    </label>
                    <label className="toggle-chip">
                      <input type="checkbox" checked={tuneDraft.codecs.av1} onChange={(event) => onUpdateTuneCodec("av1", event.target.checked)} />
                      <span>AV1</span>
                    </label>
                  </div>
                </label>
              ) : null}

              <label>
                <span>{t("tune.fixedDimension")}</span>
                <input
                  className="tuning-number-input"
                  value={tuneDraft.fixedDimension}
                  onChange={(event) => onUpdateTuneDraft("fixedDimension", event.target.value)}
                  inputMode="numeric"
                  disabled={tuneDraft.parameter === "dimension"}
                />
              </label>
              <label>
                <span>{t("tune.fixedQuality")}</span>
                <input
                  className="tuning-number-input"
                  value={tuneDraft.fixedQuality}
                  onChange={(event) => onUpdateTuneDraft("fixedQuality", event.target.value)}
                  inputMode="numeric"
                  disabled={tuneDraft.parameter === "quality"}
                />
              </label>
              <label className="full-width">
                <span>{t("tune.fixedCodec")}</span>
                <div className="checkbox-grid">
                  <label className={`toggle-chip${tuneDraft.fixedCodec === "h264" ? " active" : ""}`}>
                    <input
                      type="radio"
                      name="tune-fixed-codec"
                      checked={tuneDraft.fixedCodec === "h264"}
                      disabled={tuneDraft.parameter === "codec"}
                      onChange={() => onUpdateTuneDraft("fixedCodec", "h264")}
                    />
                    <span>H.264</span>
                  </label>
                  <label className={`toggle-chip${tuneDraft.fixedCodec === "h265" ? " active" : ""}`}>
                    <input
                      type="radio"
                      name="tune-fixed-codec"
                      checked={tuneDraft.fixedCodec === "h265"}
                      disabled={tuneDraft.parameter === "codec"}
                      onChange={() => onUpdateTuneDraft("fixedCodec", "h265")}
                    />
                    <span>H.265</span>
                  </label>
                  <label className={`toggle-chip${tuneDraft.fixedCodec === "av1" ? " active" : ""}`}>
                    <input
                      type="radio"
                      name="tune-fixed-codec"
                      checked={tuneDraft.fixedCodec === "av1"}
                      disabled={tuneDraft.parameter === "codec"}
                      onChange={() => onUpdateTuneDraft("fixedCodec", "av1")}
                    />
                    <span>AV1</span>
                  </label>
                </div>
              </label>
              <label className="toggle-row">
                <span>{t("tune.dropAudio")}</span>
                <input type="checkbox" checked={tuneDraft.dropAudio} onChange={(event) => onUpdateTuneDraft("dropAudio", event.target.checked)} />
              </label>
            </div>
            <div className="inline-actions">
              <button type="button" className="primary-button icon-button" disabled={isWorking} onClick={onRunTune}>
                <Play size={16} />
                <span>{t("tune.run")}</span>
              </button>
            </div>
          </div>

          <div className="tuning-results">
            <div className="panel-header compact-header">
              <div>
                <strong>{t("tune.outputs")}</strong>
                <p className="muted">{tuningJob?.summary_message ?? t("tune.noRun")}</p>
              </div>
            </div>
            {tuningVariants.length ? (
              <div className="tuning-result-list">
                {tuningVariants.map(({ item, variant, generatedFile }) => (
                  <article key={item.id} className="job-item-row tuning-result-row">
                    <div>
                      <strong>{variant?.label ?? item.item_key}</strong>
                      <p className="row-subtitle break-value">{item.output_ref || item.message}</p>
                    </div>
                    <div className="inline-actions">
                      <span className={`state-pill state-${item.status}`}>{item.status}</span>
                      <button
                        type="button"
                        className="mini-button icon-button"
                        disabled={!generatedFile}
                        onClick={() => generatedFile && onOpenVariantFile(generatedFile.id)}
                      >
                        <Eye size={16} />
                        <span>{t("tune.openResult")}</span>
                      </button>
                      <button
                        type="button"
                        className="mini-button icon-button"
                        disabled={item.status !== "completed" || !variant}
                        onClick={() => onPromoteVariant(variant)}
                      >
                        <Save size={16} />
                        <span>{t("tune.saveProfile")}</span>
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <div className="empty-state compact">
                <h3>{t("tune.noOutputsTitle")}</h3>
                <p>{t("tune.noOutputsBody")}</p>
              </div>
            )}

            <div className="job-events-block">
              <h4>{t("tune.events")}</h4>
              <pre className="log-console details-log-console">
                {tuningEvents.length
                  ? tuningEvents.map((event) => `${formatDate(event.created_at)}  ${event.level.toUpperCase()}  ${event.message}`).join("\n")
                  : t("tune.noEvents")}
              </pre>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
