import { Globe, HardDrive, ListTodo, LoaderCircle, ScanSearch, Search, Server, Settings2, Sparkles, SunMoon, TextSearch } from "lucide-react";

export default function AppHeader({
  healthState,
  backendLabel,
  actionError,
  actionMessage,
  liveSourceLabel,
  pendingJobsCount,
  hasActiveQueue,
  source,
  isWorking,
  locale,
  visualMode,
  librarySearchQuery,
  t,
  onScanSource,
  onOpenLogs,
  onOpenJobs,
  onOpenSettings,
  onLibrarySearchChange,
  onToggleLocale,
  onCycleVisualMode
}) {
  return (
    <>
      <header className="topbar panel">
        <div className="topbar-side topbar-side-left">
          <div className="topbar-status-cluster">
            <span className="topbar-chip" title={t("header.source")}>
              <HardDrive size={14} />
              <span className="topbar-chip-text">{liveSourceLabel}</span>
            </span>
            <span className={`topbar-chip status-chip status-chip-${healthState}`} title={backendLabel}>
              <Server size={14} />
              <span className="topbar-chip-text">{backendLabel}</span>
            </span>
          </div>
        </div>

        <div className="topbar-center">
          <div className="topbar-brand">
            <span className="topbar-brand-mark" aria-hidden="true" />
            <strong>{t("app.brand")}</strong>
          </div>
        </div>

        <div className="topbar-side topbar-side-right">
          <label className="topbar-search-shell" aria-label={t("header.search")}>
            <Search size={15} className="topbar-search-icon" />
            <input
              type="search"
              className="topbar-search-input"
              value={librarySearchQuery}
              placeholder={t("header.searchPlaceholder")}
              onChange={(event) => onLibrarySearchChange(event.target.value)}
            />
          </label>

          <div className="toolbar-actions">
          <button
            type="button"
            className="ghost-button icon-only-button"
            disabled={!source || isWorking}
            aria-label={t("header.scanSource")}
            title={t("header.scanSource")}
            onClick={onScanSource}
          >
            <ScanSearch size={16} />
          </button>
          <button
            type="button"
            className="ghost-button icon-only-button"
            aria-label={t("header.logs")}
            title={t("header.logs")}
            onClick={onOpenLogs}
          >
            <TextSearch size={16} />
          </button>
          <button
            type="button"
            className={`ghost-button icon-only-button ${hasActiveQueue ? "activity-button" : ""}`}
            aria-label={t("header.jobs")}
            title={t("header.jobs")}
            onClick={onOpenJobs}
          >
            {hasActiveQueue ? <LoaderCircle size={16} className="spinning-icon" /> : <ListTodo size={16} />}
            {hasActiveQueue ? (
              <span className="icon-badge" aria-label={t("header.queue")}>
                {pendingJobsCount}
              </span>
            ) : null}
          </button>
          <button
            type="button"
            className="ghost-button icon-only-button"
            aria-label={t("header.locale")}
            title={`${t("header.locale")}: ${locale.toUpperCase()}`}
            onClick={onToggleLocale}
          >
            <Globe size={16} />
            <span className="icon-pill">{locale.toUpperCase()}</span>
          </button>
          <button
            type="button"
            className="ghost-button icon-only-button"
            aria-label={t("header.theme")}
            title={`${t("header.theme")}: ${t(`theme.${visualMode}`)}`}
            onClick={onCycleVisualMode}
          >
            {visualMode === "casino" ? <Sparkles size={16} /> : <SunMoon size={16} />}
          </button>
          <button
            type="button"
            className="primary-button icon-only-button"
            aria-label={t("header.settings")}
            title={t("header.settings")}
            onClick={onOpenSettings}
          >
            <Settings2 size={16} />
          </button>
          </div>
        </div>
      </header>

      {actionError ? <p className="topbar-notice topbar-notice-error">{actionError}</p> : null}
      {!actionError && actionMessage ? <p className="topbar-notice">{actionMessage}</p> : null}
    </>
  );
}
