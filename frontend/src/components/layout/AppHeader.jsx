import { Globe, ListTodo, ScanSearch, Settings2, Sparkles, SunMoon, TextSearch } from "lucide-react";

export default function AppHeader({
  healthState,
  backendLabel,
  actionError,
  actionMessage,
  liveSourceLabel,
  liveSourceMeta,
  queueSummary,
  queueStatus,
  source,
  isWorking,
  locale,
  visualMode,
  t,
  onScanSource,
  onOpenLogs,
  onOpenJobs,
  onOpenSettings,
  onToggleLocale,
  onCycleVisualMode
}) {
  return (
    <header className="topbar panel">
      <div className="brand-block compact-brand-block">
        <div className="brand-row">
          <p className="eyebrow">{t("app.brand")}</p>
          <h1>{t("app.title")}</h1>
          <span className={`status-pill status-pill-${healthState}`}>{backendLabel}</span>
        </div>
        {actionError ? <p className="feedback error">{actionError}</p> : null}
        {actionMessage ? <p className="feedback">{actionMessage}</p> : null}
      </div>

      <div className="toolbar">
        <div className="toolbar-strip">
          <div className="toolbar-inline-card">
            <span className="toolbar-label">{t("header.source")}</span>
            <strong>{liveSourceLabel}</strong>
            <span className="toolbar-meta">{liveSourceMeta}</span>
          </div>

          <div className="toolbar-inline-card">
            <span className="toolbar-label">{t("header.queue")}</span>
            <strong>{queueSummary}</strong>
            <span className="toolbar-meta">{t("app.queueRuntime", { status: queueStatus })}</span>
          </div>
        </div>

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
            className="ghost-button icon-only-button"
            aria-label={t("header.jobs")}
            title={t("header.jobs")}
            onClick={onOpenJobs}
          >
            <ListTodo size={16} />
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
  );
}
