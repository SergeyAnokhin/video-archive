import { Save, X } from "lucide-react";

export default function PromotionModal({ isOpen, promotionDraft, isWorking, onClose, onUpdate, onSubmit, t }) {
  if (!isOpen || !promotionDraft) {
    return null;
  }

  return (
    <div className="overlay-backdrop" onClick={onClose}>
      <section className="overlay panel modal-shell promote-shell" onClick={(event) => event.stopPropagation()}>
        <div className="panel-header">
          <div>
            <p className="section-kicker">{t("promotion.kicker")}</p>
            <h2>{t("promotion.title")}</h2>
          </div>
          <button type="button" className="ghost-button icon-only-button" aria-label={t("common.close")} title={t("common.close")} onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        <div className="form-grid">
          <label className="full-width">
            <span>{t("promotion.name")}</span>
            <input value={promotionDraft.name} onChange={(event) => onUpdate("name", event.target.value)} />
          </label>
          <label className="toggle-row">
            <span>{t("promotion.markDefault")}</span>
            <input type="checkbox" checked={promotionDraft.isDefault} onChange={(event) => onUpdate("isDefault", event.target.checked)} />
          </label>
        </div>
        <div className="note-card">
          <strong>{promotionDraft.variant.label}</strong>
          <p>
            Codec {promotionDraft.variant.video_codec.toUpperCase()} - Max dimension {promotionDraft.variant.max_dimension ?? t("promotion.sourceDimension")} -{" "}
            {promotionDraft.variant.quality_value ? `CRF ${promotionDraft.variant.quality_value}` : t("promotion.defaultQuality")}
          </p>
        </div>
        <div className="inline-actions">
          <button type="button" className="primary-button icon-button" disabled={isWorking || !promotionDraft.name.trim()} onClick={onSubmit}>
            <Save size={16} />
            <span>{t("promotion.save")}</span>
          </button>
        </div>
      </section>
    </div>
  );
}
