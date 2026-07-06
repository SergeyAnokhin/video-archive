import { Play, X } from "lucide-react";
import { formatDirectoryLabel } from "../../features/source/sourceHelpers";

export default function ConversionModal({
  isOpen,
  conversionDraft,
  conversionProfiles,
  formatProfileLabel,
  isWorking,
  onClose,
  onUpdateProfileId,
  onUpdateMode,
  onSubmit,
  t
}) {
  if (!isOpen || !conversionDraft) {
    return null;
  }

  return (
    <div className="overlay-backdrop" onClick={onClose}>
      <section className="overlay panel modal-shell convert-shell" onClick={(event) => event.stopPropagation()}>
        <div className="panel-header">
          <div>
            <p className="section-kicker">{t("conversionModal.kicker")}</p>
            <h2>{conversionDraft.scope === "file" ? t("conversionModal.fileTitle") : t("conversionModal.directoryTitle")}</h2>
          </div>
          <button type="button" className="ghost-button icon-only-button" aria-label={t("common.close")} title={t("common.close")} onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        <div className="convert-layout">
          <div className="note-card">
            <strong>
              {conversionDraft.scope === "file"
                ? conversionDraft.fileName || t("conversionModal.fileTitle")
                : formatDirectoryLabel(conversionDraft.relativePath, t)}
            </strong>
            <p>{t("conversionModal.description")}</p>
          </div>

          <div className="form-grid">
            <label className="full-width">
              <span>{t("conversionModal.savedProfile")}</span>
              <select value={conversionDraft.profileId} onChange={(event) => onUpdateProfileId(event.target.value)}>
                {conversionProfiles.map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {formatProfileLabel(profile)}
                  </option>
                ))}
              </select>
            </label>

            <label>
              <span>{t("conversionModal.mode")}</span>
              <select value={conversionDraft.mode} onChange={(event) => onUpdateMode(event.target.value)}>
                <option value="production">{t("conversionModal.production")}</option>
                <option value="test">{t("conversionModal.test")}</option>
              </select>
            </label>
          </div>

          <div className="inline-actions">
            <button type="button" className="ghost-button icon-button" onClick={onClose}>
              <X size={16} />
              <span>{t("common.cancel")}</span>
            </button>
            <button type="button" className="primary-button icon-button" disabled={isWorking} onClick={onSubmit}>
              <Play size={16} />
              <span>{t("conversionModal.start")}</span>
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
