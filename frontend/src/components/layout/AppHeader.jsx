import { Globe, ListTodo, LoaderCircle, ScanSearch, Search, Settings2, Sparkles, SunMoon, TextSearch } from "lucide-react";

export default function AppHeader({
  healthState,
  backendTooltip,
  actionError,
  actionMessage,
  hasSource,
  pendingJobsCount,
  hasActiveQueue,
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
        <div className="topbar-brand-group">
          <div className="topbar-brand">
            <span className="topbar-brand-logo" aria-hidden="true">
              <svg viewBox="0 0 48 48" focusable="false">
                <defs>
                  <linearGradient id="backend-logo-gradient" x1="0%" x2="100%" y1="0%" y2="100%">
                    <stop offset="0%" stopColor="var(--accent)" />
                    <stop offset="100%" stopColor="var(--accent-strong)" />
                  </linearGradient>
                </defs>
                <rect x="4" y="6" width="40" height="36" rx="11" fill="rgba(10, 18, 30, 0.88)" stroke="rgba(143, 179, 255, 0.24)" />
                <circle cx="15" cy="16" r="4" fill="url(#backend-logo-gradient)" />
                <circle cx="33" cy="16" r="4" fill="url(#backend-logo-gradient)" />
                <circle cx="24" cy="31" r="5" fill="url(#backend-logo-gradient)" />
                <path d="M18.5 18.5L21.5 27M29.5 18.5L26.5 27M19 16H29" stroke="rgba(216, 230, 255, 0.92)" strokeWidth="2.2" strokeLinecap="round" />
              </svg>
            </span>
            <strong>{t("app.brand")}</strong>
          </div>
          <span
            className={`backend-health-indicator backend-health-indicator-${healthState}`}
            title={backendTooltip}
            aria-label={backendTooltip}
          />
        </div>

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
            disabled={!hasSource || isWorking}
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
      </header>

      {actionError ? <p className="topbar-notice topbar-notice-error">{actionError}</p> : null}
      {!actionError && actionMessage ? <p className="topbar-notice">{actionMessage}</p> : null}
    </>
  );
}
