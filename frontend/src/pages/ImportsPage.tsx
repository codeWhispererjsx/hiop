import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Feedback } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { StatCard } from "../components/StatCard";
import { StatusBadge } from "../components/StatusBadge";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import type { ImportSessionStatus, User } from "../lib/types";
import { PageTitle } from "./DashboardPage";
import "../styles/imports.css";

export default function ImportsPage() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<ImportSessionStatus | "">("");
  const [page, setPage] = useState(1);
  const [sortAsc, setSortAsc] = useState(false);
  const sessions = useRequest(
    () =>
      endpoints.importSessions({
        search: search || undefined,
        status: status || undefined,
        page,
        page_size: 25,
      }),
    [search, status, page],
  );
  const me = useRequest<User>(endpoints.me, []);
  const data = sessions.data;
  const rows = useMemo(
    () =>
      [...(data?.items ?? [])].sort(
        (a, b) =>
          (sortAsc ? 1 : -1) * a.uploaded_at.localeCompare(b.uploaded_at),
      ),
    [data, sortAsc],
  );
  const recent = data?.items ?? [];
  const active = recent.filter((item) =>
    ["uploaded", "validating", "processing", "review_required", "ready", "importing"].includes(item.status),
  ).length;
  const completed = recent.filter((item) => item.status === "completed").length;
  const failed = recent.filter((item) => item.status === "failed").length;
  const pending = recent.reduce(
    (sum, item) =>
      sum +
      (item.match_summary.total_valid_rows ?? 0) -
      (item.match_summary.resolved ?? 0),
    0,
  );
  const conflicts = recent.reduce(
    (sum, item) => sum + (item.match_summary.conflicts ?? 0),
    0,
  );
  const createNew = recent.reduce(
    (sum, item) => sum + (item.match_summary.suggested_new_devices ?? 0),
    0,
  );
  const lastSuccess = recent.find(
    (item) => item.status === "completed",
  )?.processing_completed_at;

  const cancel = async (id: string) => {
    if (
      !window.confirm(
        "Cancel this unprocessed import session? Staging history will be retained.",
      )
    )
      return;
    try {
      await endpoints.cancelImport(id);
      await sessions.reload();
    } catch (error) {
      window.alert(
        error instanceof Error ? error.message : "Unable to cancel import.",
      );
    }
  };
  const exportErrors = async (id: string) => {
    try {
      const result = await endpoints.exportImportErrors(id);
      const url = URL.createObjectURL(result.blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = result.filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      window.alert(
        error instanceof Error
          ? error.message
          : "Unable to export validation errors.",
      );
    }
  };

  return (
    <DashboardLayout>
      <PageTitle
        eyebrow="Inventory onboarding"
        title="Inventory imports"
        copy="Upload, validate, match, and review existing inventory without changing official Devices."
        action={
          me.data?.role === "admin" ? (
            <Link className="primary-action" to="/imports/new">
              <Icon name="import" />
              Start new import
            </Link>
          ) : undefined
        }
      />
      <section className="stats-grid import-stats">
        <StatCard
          label="Total sessions"
          value={data?.total ?? 0}
          detail="Backend-retained import history"
          icon="import"
          trend="Sessions"
        />
        <StatCard
          label="Active sessions"
          value={active}
          detail="Uploaded or processing in this view"
          icon="clock"
          tone="warning"
          trend="Active"
        />
        <StatCard
          label="Completed"
          value={completed}
          detail={
            lastSuccess
              ? `Last ${new Date(lastSuccess).toLocaleString()}`
              : "No completed session in view"
          }
          icon="check"
          tone="success"
          trend="Recent"
        />
        <StatCard
          label="Failed"
          value={failed}
          detail="Sessions requiring administrator review"
          icon="warning"
          tone="danger"
          trend="Recent"
        />
        <StatCard
          label="Pending review"
          value={Math.max(0, pending)}
          detail="Validated rows not yet resolved"
          icon="search"
          trend="Rows"
        />
        <StatCard
          label="Conflicts"
          value={conflicts}
          detail="Identifier or hierarchy conflicts"
          icon="warning"
          tone="danger"
          trend="Rows"
        />
        <StatCard
          label="Create-new"
          value={createNew}
          detail="Prepared recommendations only"
          icon="devices"
          trend="Rows"
        />
      </section>
      <section className="panel import-management">
        <header className="section-head">
          <div>
            <h2>Recent import sessions</h2>
            <p>
              Resume backend-persisted work or inspect validation and matching
              results.
            </p>
          </div>
        </header>
        <div className="toolbar import-toolbar">
          <label className="search-field">
            <Icon name="search" />
            <span className="sr-only">Search filenames</span>
            <input
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
              placeholder="Search filename"
            />
          </label>
          <label>
            <span className="sr-only">Filter status</span>
            <select
              value={status}
              onChange={(event) => {
                setStatus(event.target.value as ImportSessionStatus | "");
                setPage(1);
              }}
            >
              <option value="">All statuses</option>
              {[
                "uploaded",
                "validating",
                "processing",
                "review_required",
                "ready",
                "importing",
                "completed",
                "partial",
                "failed",
                "cancelled",
                "rolled_back",
              ].map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          <button
            className="secondary-action"
            onClick={() => setSortAsc((value) => !value)}
          >
            Uploaded {sortAsc ? "oldest first" : "newest first"}
          </button>
        </div>
        {sessions.loading || sessions.error ? (
          <Feedback
            loading={sessions.loading}
            error={sessions.error}
            onRetry={sessions.reload}
          />
        ) : !rows.length ? (
          <Feedback
            emptyTitle="No import sessions"
            empty="Start a CSV or XLSX import when you are ready to stage inventory."
          />
        ) : (
          <div className="table-wrap">
            <table className="data-table import-session-table">
              <thead>
                <tr>
                  <th>File</th>
                  <th>Uploaded</th>
                  <th>Status</th>
                  <th>Rows</th>
                  <th>Valid</th>
                  <th>Warning</th>
                  <th>Invalid</th>
                  <th>Duplicate</th>
                  <th>Matched</th>
                  <th>Conflicts</th>
                  <th>Progress</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((item) => {
                  const progress = item.total_rows
                    ? Math.round((item.processed_rows / item.total_rows) * 100)
                    : item.status === "uploaded"
                      ? 0
                      : 100;
                  return (
                    <tr key={item.id}>
                      <td>
                        <strong>{item.original_filename}</strong>
                        <small>{item.uploaded_by ?? "Former user"}</small>
                      </td>
                      <td>{new Date(item.uploaded_at).toLocaleString()}</td>
                      <td>
                        <StatusBadge status={item.status} />
                      </td>
                      <td>{item.total_rows}</td>
                      <td>{item.validation_summary.valid ?? 0}</td>
                      <td>{item.validation_summary.warning ?? 0}</td>
                      <td>
                        {item.validation_summary.invalid ?? item.failed_rows}
                      </td>
                      <td>
                        {item.validation_summary.duplicate ??
                          item.duplicate_rows}
                      </td>
                      <td>{item.matched_rows}</td>
                      <td>{item.match_summary.conflicts ?? 0}</td>
                      <td>
                        <span className="progress-label">{progress}%</span>
                        <span className="progress-track">
                          <i style={{ width: `${progress}%` }} />
                        </span>
                      </td>
                      <td>
                        <div className="row-actions import-actions">
                          <Link to={`/imports/${item.id}`}>Continue</Link>
                          {item.failed_rows > 0 && (
                            <button onClick={() => void exportErrors(item.id)}>
                              Errors CSV
                            </button>
                          )}
                          {me.data?.role === "admin" &&
                            item.status === "uploaded" && (
                              <button onClick={() => void cancel(item.id)}>
                                Cancel
                              </button>
                            )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {data && data.pages > 1 && (
          <nav className="pagination" aria-label="Import session pages">
            <button disabled={page <= 1} onClick={() => setPage(page - 1)}>
              Previous
            </button>
            <span>
              Page {page} of {data.pages}
            </span>
            <button
              disabled={page >= data.pages}
              onClick={() => setPage(page + 1)}
            >
              Next
            </button>
          </nav>
        )}
      </section>
    </DashboardLayout>
  );
}
