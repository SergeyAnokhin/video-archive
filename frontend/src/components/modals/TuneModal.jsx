import { Play, Save, X } from "lucide-react";

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
  onUpdateTuneCodec,
  onRunTune,
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
            <div className="form-grid">
              <label className="full-width">
                <span>{t("tune.dimensions")}</span>
                <input value={tuneDraft.dimensionsText} onChange={(event) => onUpdateTuneDraft("dimensionsText", event.target.value)} placeholder="1000, 900, 800" />
              </label>
              <label className="full-width">
                <span>{t("tune.qualities")}</span>
                <input value={tuneDraft.qualitiesText} onChange={(event) => onUpdateTuneDraft("qualitiesText", event.target.value)} placeholder="20, 24, 28" />
              </label>
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
                {tuningVariants.map(({ item, variant }) => (
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
