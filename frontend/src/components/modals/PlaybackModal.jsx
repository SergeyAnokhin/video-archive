import { X } from "lucide-react";

export default function PlaybackModal({ isOpen, playbackTarget, onClose, t }) {
  if (!isOpen || !playbackTarget) {
    return null;
  }

  return (
    <div className="overlay-backdrop" onClick={onClose}>
      <section className="overlay panel modal-shell playback-shell" onClick={(event) => event.stopPropagation()}>
        <div className="panel-header">
          <div>
            <p className="section-kicker">{t("playbackModal.kicker")}</p>
            <h2>{playbackTarget.file_name}</h2>
          </div>
          <button type="button" className="ghost-button icon-only-button" aria-label={t("common.close")} title={t("common.close")} onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        <div className="video-player-shell">
          <video controls className="video-player" src={playbackTarget.embedded_url} />
        </div>
        <div className="note-card">
          <strong>{t("playbackModal.target")}</strong>
          <p className="break-value">{playbackTarget.path}</p>
        </div>
      </section>
    </div>
  );
}
