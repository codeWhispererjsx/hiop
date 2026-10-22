import { useState } from "react";
import { Link } from "react-router-dom";
import { Feedback } from "../components/Feedback";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import { formatDateTime } from "../lib/dateTime";
import { PageTitle } from "./DashboardPage";

function formatBytes(value: number | null) {
  if (value === null) return "Unavailable";
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  return `${(value / 1024 ** 3).toFixed(1)} GB`;
}

function readableStatus(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export default function ThisComputerPage() {
  const operations = useRequest(endpoints.localOperationsStatus, []);
  const [downloading, setDownloading] = useState(false);
  const [reportError, setReportError] = useState("");

  const downloadReport = async () => {
    setDownloading(true);
    setReportError("");
    try {
      const { blob, filename } = await endpoints.downloadLocalSupportReport();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      setReportError(error instanceof Error ? error.message : "Support report could not be downloaded.");
    } finally {
      setDownloading(false);
    }
  };

  if (operations.loading) return <DashboardLayout><Feedback loading /></DashboardLayout>;
  if (operations.error || !operations.data) return <DashboardLayout><Feedback error={operations.error || "Local operations status is unavailable."} /></DashboardLayout>;

  const status = operations.data;
  const addresses = status.network.ipv4_addresses.length ? status.network.ipv4_addresses.join(", ") : "Not detected";

  return <DashboardLayout>
    <PageTitle eyebrow="Hotel operations" title="Site Server" copy="Check this HIOP installation, local database, monitoring, backups, and recovery information." />
    <section className="this-computer-status" aria-label="HIOP local operations status">
      <article><span>HIOP service</span><strong>{readableStatus(status.service.status)}</strong><p>{status.service.details}</p></article>
      <article><span>HIOP database</span><strong>{readableStatus(status.database.status)}</strong><p>{status.database.details}</p></article>
      <article><span>Network connection</span><strong>{addresses}</strong><p>{status.network.details}</p></article>
      <article><span>Automation scheduler</span><strong>{readableStatus(status.scheduler.status)}</strong><p>{status.scheduler.enabled_jobs} scheduled job(s) currently registered.</p></article>
      <article><span>Last discovery</span><strong>{status.discovery.last_run ? formatDateTime(status.discovery.last_run) : "No scan recorded"}</strong><p>{readableStatus(status.discovery.result)} · {status.discovery.hosts_completed} of {status.discovery.hosts_total} hosts checked.</p></article>
      <article><span>Monitored devices</span><strong>{status.monitored_devices.total ?? "Unavailable"}</strong><p>{status.monitored_devices.last_scan ? `Last check ${formatDateTime(status.monitored_devices.last_scan)} · ${status.monitored_devices.last_result}.` : "No monitoring scan has been recorded."}</p></article>
      <article id="backup-recovery"><span>Backup and recovery</span><strong>{readableStatus(status.backup.status)}</strong><p>{status.backup.details} {status.backup.last_backup ? `Last backup ${formatDateTime(status.backup.last_backup)}.` : ""} Restore test: {readableStatus(status.backup.restore_status)}.</p>{status.backup.next_backup&&<small>Next scheduled backup: {formatDateTime(status.backup.next_backup)}</small>}</article>
      <article><span>Storage</span><strong>{formatBytes(status.storage.available_bytes)} free</strong><p>HIOP database: {formatBytes(status.storage.database_bytes)}. {status.storage.details}</p></article>
    </section>

    <section className="this-computer-guide" aria-label="Local operations quick actions">
      <header><span>Quick actions</span><h2>Manage this HIOP installation</h2></header>
      <nav className="this-computer-actions">
        <Link className="primary-action" to="/discovery-intelligence">Run device discovery</Link>
        <Link className="secondary-action" to="/settings">Open HIOP settings</Link>
        <a className="secondary-action" href="#diagnostics">View service diagnostics</a>
        <button className="secondary-action" type="button" disabled={downloading} onClick={() => void downloadReport()}>{downloading ? "Preparing report…" : "Download support report"}</button>
        <button className="secondary-action" type="button" onClick={() => document.getElementById("backup-recovery")?.scrollIntoView({ behavior: "smooth" })}>View backup and recovery</button>
      </nav>
      <p className="this-computer-note">This HIOP desktop installation already runs its local collector and does not need a separate Collector download.</p>
      <p className="this-computer-note">The support report includes installation status and scoped operational counts. It excludes credentials, tokens, private keys, device addresses, MAC addresses, and backup paths. Share it only with authorized HIOP support personnel.</p>
      {reportError&&<p role="alert">{reportError}</p>}
    </section>

    <section className="this-computer-guide" id="diagnostics" aria-label="Recent service diagnostics">
      <header><span>Diagnostics</span><h2>Recent errors</h2></header>
      {status.recent_errors.length ? <ul className="this-computer-errors">{status.recent_errors.map((error,index)=><li key={`${error.job_type}-${error.occurred_at}-${index}`}><strong>{error.job_type}</strong><time>{formatDateTime(error.occurred_at)}</time><p>{error.message}</p></li>)}</ul> : <p>No recent background task errors were reported.</p>}
      <p className="this-computer-note">Detailed infrastructure backups and restore operations are available only to the platform administrator on hosted installations.</p>
    </section>
  </DashboardLayout>;
}
