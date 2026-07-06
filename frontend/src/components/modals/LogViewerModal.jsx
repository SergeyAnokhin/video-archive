import { FilterX, X } from "lucide-react";

export default function LogViewerModal({
  isOpen,
  onClose,
  logFilters,
  onChangeLogFilter,
  onClearFilters,
  logEvents,
  logConsoleRef,
  formatDate,
  t
}) {
  if (!isOpen) {
    return null;
  }

  return (
    <div className="overlay-backdrop" onClick={onClose}>
      <section className="overlay panel modal-shell logs-shell" onClick={(event) => event.stopPropagation()}>
        <div className="panel-header">
          <div>
            <p className="section-kicker">{t("logs.kicker")}</p>
            <h2>{t("logs.title")}</h2>
          </div>
          <button type="button" className="ghost-button icon-only-button" aria-label={t("common.close")} title={t("common.close")} onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        <div className="log-filter-grid">
          <label>
            <span>{t("logs.jobId")}</span>
            <input value={logFilters.jobId} onChange={(event) => onChangeLogFilter("jobId", event.target.value)} />
          </label>
          <label>
            <span>{t("logs.fileId")}</span>
            <input value={logFilters.fileId} onChange={(event) => onChangeLogFilter("fileId", event.target.value)} />
          </label>
          <label>
            <span>{t("logs.level")}</span>
            <select value={logFilters.level} onChange={(event) => onChangeLogFilter("level", event.target.value)}>
              <option value="">{t("common.allLevels")}</option>
              <option value="debug">{t("logs.debug")}</option>
              <option value="info">{t("logs.info")}</option>
              <option value="warning">{t("logs.warning")}</option>
              <option value="error">{t("logs.error")}</option>
            </select>
          </label>
          <div className="inline-actions align-end">
            <button type="button" className="ghost-button icon-button" onClick={onClearFilters}>
              <FilterX size={16} />
              <span>{t("logs.clear")}</span>
            </button>
          </div>
        </div>
        <pre ref={logConsoleRef} className="log-console tall-console">
          {logEvents.length
            ? logEvents.map((event) => `${formatDate(event.created_at)}  ${event.level.toUpperCase()}  ${event.message}`).join("\n")
            : t("logs.empty")}
        </pre>
      </section>
    </div>
  );
}
