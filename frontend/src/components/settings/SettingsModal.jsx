import { X } from "lucide-react";
import { renderSettingsDetail } from "./SettingsSections";

export default function SettingsModal(props) {
  const { isOpen, onClose, settingsSections, selectedSettingsSection, onSelectSection } = props;

  if (!isOpen) {
    return null;
  }

  const selectedSectionLabel =
    settingsSections.find((section) => section.id === selectedSettingsSection)?.label ?? props.t("settings.title");

  return (
    <div className="overlay-backdrop" onClick={onClose}>
      <section className="overlay panel modal-shell settings-shell" onClick={(event) => event.stopPropagation()}>
        <div className="panel-header">
          <div>
            <p className="section-kicker">{props.t("settings.title")}</p>
            <h2>{selectedSectionLabel}</h2>
          </div>
          <button type="button" className="ghost-button icon-only-button" aria-label={props.t("common.close")} title={props.t("common.close")} onClick={onClose}>
            <X size={16} />
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
