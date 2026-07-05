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
  formatJobScope,
  formatJobTypeLabel
}) {
  if (!isOpen) {
    return null;
  }

  return (
    <div className="overlay-backdrop" onClick={onClose}>
      <section className="overlay panel modal-shell" onClick={(event) => event.stopPropagation()}>
        <div className="panel-header">
          <div>
            <p className="section-kicker">Tasks and jobs</p>
            <h2>Recent jobs</h2>
          </div>
          <button type="button" className="ghost-button" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="jobs-grid">
          {jobs.length ? (
            <>
              <div className="job-list">
                {jobs.map((job) => (
                  <button
                    key={job.id}
                    type="button"
                    className={`job-card job-select-card ${selectedJobId === job.id ? "active" : ""}`}
                    onClick={() => onSelectJob(job.id)}
                  >
                    <div className="job-header">
                      <strong>{formatJobTypeLabel(job.job_type)}</strong>
                      <span className={`state-pill state-${job.status}`}>{job.status}</span>
                    </div>
                    <p>{formatJobScope(job)}</p>
                    <p className="muted">{job.summary_message || "No summary available."}</p>
                    <p className="muted">Items {job.item_counts.completed}/{job.item_counts.total}</p>
                  </button>
                ))}
              </div>
              <section className="job-detail panel">
                {selectedJob ? (
                  <>
                    <div className="job-detail-header">
                      <div>
                        <p className="section-kicker">Job detail</p>
                        <h3>
                          {formatJobTypeLabel(selectedJob.job_type)} - {formatJobScope(selectedJob)}
                        </h3>
                      </div>
                      <div className="inline-actions">
                        <button type="button" className="ghost-button" onClick={() => onRefreshJob(selectedJob.id)}>
                          Refresh
                        </button>
                        <button
                          type="button"
                          className="ghost-button"
                          disabled={!["queued", "running"].includes(selectedJob.status)}
                          onClick={() => onCancelJob(selectedJob.id)}
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          className="ghost-button"
                          disabled={!["completed", "failed", "cancelled"].includes(selectedJob.status)}
                          onClick={() => onRestartJob(selectedJob.id)}
                        >
                          Restart
                        </button>
                        <button
                          type="button"
                          className="ghost-button"
                          onClick={() => onOpenLogViewer({ jobId: selectedJob.id, fileId: "", level: "" })}
                        >
                          Open in logs
                        </button>
                      </div>
                    </div>
                    <div className="job-meta-grid">
                      <div>
                        <span className="muted">Status</span>
                        <strong>{selectedJob.status}</strong>
                      </div>
                      <div>
                        <span className="muted">Queued</span>
                        <strong>{selectedJob.item_counts.queued}</strong>
                      </div>
                      <div>
                        <span className="muted">Running</span>
                        <strong>{selectedJob.item_counts.running}</strong>
                      </div>
                      <div>
                        <span className="muted">Completed</span>
                        <strong>{selectedJob.item_counts.completed}</strong>
                      </div>
                      <div>
                        <span className="muted">Failed</span>
                        <strong>{selectedJob.item_counts.failed}</strong>
                      </div>
                      <div>
                        <span className="muted">Cancelled</span>
                        <strong>{selectedJob.item_counts.cancelled}</strong>
                      </div>
                    </div>
                    <p className="muted">{selectedJob.summary_message || "No summary available."}</p>
                    <div className="job-items-block">
                      <h4>Items</h4>
                      <div className="job-items-list">
                        {jobItems.map((item) => (
                          <article key={item.id} className="job-item-row">
                            <div>
                              <strong>{item.file_name || item.item_key || "Scope item"}</strong>
                              <p className="row-subtitle">{item.relative_path || item.message || "-"}</p>
                            </div>
                            <span className={`state-pill state-${item.status}`}>{item.status}</span>
                          </article>
                        ))}
                      </div>
                    </div>
                    <div className="job-events-block">
                      <h4>Events</h4>
                      <pre className="log-console">
                        {jobEvents.length
                          ? jobEvents.map((event) => `${formatDate(event.created_at)}  ${event.level.toUpperCase()}  ${event.message}`).join("\n")
                          : "No events yet."}
                      </pre>
                    </div>
                  </>
                ) : (
                  <div className="empty-state compact">
                    <h3>No job selected</h3>
                    <p>Select a job to inspect its items and event stream.</p>
                  </div>
                )}
              </section>
            </>
          ) : (
            <div className="empty-state compact">
              <h3>No jobs yet</h3>
              <p>Queued scan, rescan, convert, preview, tag, and tune jobs will appear here.</p>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
