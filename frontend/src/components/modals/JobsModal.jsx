import { Ban, Folder, ImageIcon, Play, RefreshCcw, RotateCcw, SlidersHorizontal, Tag, TextSearch, X } from "lucide-react";

const JOB_TYPE_ICONS = {
  scan: Folder,
  rescan: RefreshCcw,
  convert: Play,
  preview: ImageIcon,
  tag: Tag,
  tune: SlidersHorizontal
};

export default function JobsModal({
  isOpen,
  jobs,
  selectedJobId,
  selectedJob,
  jobItems,
  jobEvents,
  onClose,
  onSelectJob,
  onRefreshJob,
  onCancelJob,
  onRestartJob,
  onOpenLogViewer,
  formatDate,
  formatStatusLabel,
  formatJobScope,
  formatJobTypeLabel,
  t
}) {
  if (!isOpen) {
    return null;
  }

  return (
    <div className="overlay-backdrop" onClick={onClose}>
      <section className="overlay panel modal-shell" onClick={(event) => event.stopPropagation()}>
        <div className="panel-header">
          <div>
            <p className="section-kicker">{t("jobs.kicker")}</p>
            <h2>{t("jobs.title")}</h2>
          </div>
          <button type="button" className="ghost-button icon-only-button" aria-label={t("common.close")} title={t("common.close")} onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        <div className="jobs-grid">
          {jobs.length ? (
            <>
              <div className="job-list">
                {jobs.map((job) => {
                  const JobTypeIcon = JOB_TYPE_ICONS[job.job_type] || Folder;
                  return (
                    <article key={job.id} className={`job-card job-select-card ${selectedJobId === job.id ? "active" : ""}`}>
                      <button type="button" className="job-select-main" onClick={() => onSelectJob(job.id)}>
                        <div className="job-card-top">
                          <span className="job-card-icon" aria-hidden="true">
                            <JobTypeIcon size={18} />
                          </span>
                          <div className="job-card-copy">
                            <div className="job-header">
                              <strong>{formatJobTypeLabel(job.job_type)}</strong>
                              <span className={`state-pill state-${job.status}`}>{formatStatusLabel(job.status)}</span>
                            </div>
                            <p className="job-scope">{formatJobScope(job)}</p>
                          </div>
                        </div>
                        <p className="muted job-summary">{job.summary_message || t("jobs.noSummary")}</p>
                        <div className="job-card-stats">
                          <span>{t("jobs.itemsProgress", { completed: job.item_counts.completed, total: job.item_counts.total })}</span>
                          <span>{t("jobs.running")}: {job.item_counts.running}</span>
                          <span>{t("jobs.failed")}: {job.item_counts.failed}</span>
                        </div>
                      </button>
                      <div className="job-card-actions">
                        <button
                          type="button"
                          className="ghost-button icon-only-button"
                          aria-label={t("jobs.openLogs")}
                          title={t("jobs.openLogs")}
                          onClick={() => onOpenLogViewer({ jobId: job.id, fileId: "", level: "" })}
                        >
                          <TextSearch size={15} />
                        </button>
                        <button
                          type="button"
                          className="ghost-button icon-only-button"
                          aria-label={t("jobs.cancel")}
                          title={t("jobs.cancel")}
                          disabled={!["queued", "running"].includes(job.status)}
                          onClick={() => onCancelJob(job.id)}
                        >
                          <Ban size={15} />
                        </button>
                        <button
                          type="button"
                          className="ghost-button icon-only-button"
                          aria-label={t("jobs.restart")}
                          title={t("jobs.restart")}
                          disabled={!["completed", "failed", "cancelled"].includes(job.status)}
                          onClick={() => onRestartJob(job.id)}
                        >
                          <RotateCcw size={15} />
                        </button>
                      </div>
                    </article>
                  );
                })}
              </div>
              <section className="job-detail panel">
                {selectedJob ? (
                  <>
                    <div className="job-detail-header">
                      <div>
                        <p className="section-kicker">{t("jobs.detail")}</p>
                        <h3>
                          {formatJobTypeLabel(selectedJob.job_type)} - {formatJobScope(selectedJob)}
                        </h3>
                        <p className="muted job-detail-status">{formatStatusLabel(selectedJob.status)}</p>
                      </div>
                      <div className="inline-actions">
                        <button type="button" className="ghost-button icon-button" onClick={() => onRefreshJob(selectedJob.id)}>
                          <RefreshCcw size={16} />
                          <span>{t("jobs.refresh")}</span>
                        </button>
                        <button
                          type="button"
                          className="ghost-button icon-button"
                          disabled={!["queued", "running"].includes(selectedJob.status)}
                          onClick={() => onCancelJob(selectedJob.id)}
                        >
                          <Ban size={16} />
                          <span>{t("jobs.cancel")}</span>
                        </button>
                        <button
                          type="button"
                          className="ghost-button icon-button"
                          disabled={!["completed", "failed", "cancelled"].includes(selectedJob.status)}
                          onClick={() => onRestartJob(selectedJob.id)}
                        >
                          <RotateCcw size={16} />
                          <span>{t("jobs.restart")}</span>
                        </button>
                        <button
                          type="button"
                          className="ghost-button icon-button"
                          onClick={() => onOpenLogViewer({ jobId: selectedJob.id, fileId: "", level: "" })}
                        >
                          <TextSearch size={16} />
                          <span>{t("jobs.openLogs")}</span>
                        </button>
                      </div>
                    </div>
                    <div className="job-meta-grid">
                      <div>
                        <span className="muted">{t("files.status")}</span>
                        <strong>{formatStatusLabel(selectedJob.status)}</strong>
                      </div>
                      <div>
                        <span className="muted">{t("jobs.queued")}</span>
                        <strong>{selectedJob.item_counts.queued}</strong>
                      </div>
                      <div>
                        <span className="muted">{t("jobs.running")}</span>
                        <strong>{selectedJob.item_counts.running}</strong>
                      </div>
                      <div>
                        <span className="muted">{t("jobs.completed")}</span>
                        <strong>{selectedJob.item_counts.completed}</strong>
                      </div>
                      <div>
                        <span className="muted">{t("jobs.failed")}</span>
                        <strong>{selectedJob.item_counts.failed}</strong>
                      </div>
                      <div>
                        <span className="muted">{t("jobs.cancelled")}</span>
                        <strong>{selectedJob.item_counts.cancelled}</strong>
                      </div>
                    </div>
                    <p className="muted">{selectedJob.summary_message || t("jobs.noSummary")}</p>
                    <div className="job-items-block">
                      <h4>{t("jobs.items")}</h4>
                      <div className="job-items-list">
                        {jobItems.map((item) => (
                          <article key={item.id} className="job-item-row">
                            <div>
                              <strong>{item.file_name || item.item_key || t("jobs.scopeItem")}</strong>
                              <p className="row-subtitle">{item.relative_path || item.message || "-"}</p>
                            </div>
                            <span className={`state-pill state-${item.status}`}>{formatStatusLabel(item.status)}</span>
                          </article>
                        ))}
                      </div>
                    </div>
                    <div className="job-events-block">
                      <h4>{t("jobs.events")}</h4>
                      <pre className="log-console">
                        {jobEvents.length
                          ? jobEvents.map((event) => `${formatDate(event.created_at)}  ${event.level.toUpperCase()}  ${event.message}`).join("\n")
                          : t("jobs.noEvents")}
                      </pre>
                    </div>
                  </>
                ) : (
                  <div className="empty-state compact">
                    <h3>{t("jobs.noSelectionTitle")}</h3>
                    <p>{t("jobs.noSelectionBody")}</p>
                  </div>
                )}
              </section>
            </>
          ) : (
            <div className="empty-state compact">
              <h3>{t("jobs.noJobsTitle")}</h3>
              <p>{t("jobs.noJobsBody")}</p>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
