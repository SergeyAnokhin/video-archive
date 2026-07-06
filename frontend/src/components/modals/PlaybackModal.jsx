import { Info, X } from "lucide-react";

export default function PlaybackModal({ isOpen, playbackTarget, onClose, onOpenInfo, t }) {
  if (!isOpen || !playbackTarget) {
    return null;
  }

  return (
    <div className="overlay-backdrop playback-backdrop" onClick={onClose}>
      <section className="overlay panel modal-shell playback-shell" onClick={(event) => event.stopPropagation()}>
        <div className="playback-floating-bar">
          <button
            type="button"
            className="ghost-button icon-only-button playback-float-button"
            aria-label={t("playbackModal.openInfo")}
            title={t("playbackModal.openInfo")}
            onClick={onOpenInfo}
          >
            <Info size={17} />
          </button>
          <button
            type="button"
            className="ghost-button icon-only-button playback-float-button"
            aria-label={t("common.close")}
            title={t("common.close")}
            onClick={onClose}
          >
            <X size={17} />
          </button>
        </div>
        <div className="video-player-shell playback-stage">
          <video autoPlay controls playsInline className="video-player playback-video" src={playbackTarget.embedded_url} />
        </div>
      </section>
    </div>
  );
}
