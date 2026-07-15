import { type FormEvent, useMemo, useState } from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import { PageTitle } from "./DashboardPage";
import { Icon } from "../components/Icon";
import { Feedback } from "../components/Feedback";
import { endpoints } from "../lib/api";
import { useRequest } from "../hooks/useRequest";
import type { LiveEvent, Scan } from "../lib/types";

type RangeResult = { ip_address: string; status: string; response_time: number | null };

export default function NetworkPage() {
  const { data, loading, error, reload } = useRequest(() => endpoints.scanHistory(100), []);
  const [network, setNetwork] = useState("10.50.20.0/24");
  const [range, setRange] = useState<RangeResult[] | null>(null);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const summary = useMemo(() => ({
    online: (data ?? []).filter(x => x.status === "Online").length,
    offline: (data ?? []).filter(x => x.status === "Offline").length,
  }), [data]);

  const run = async (kind: "all" | "range") => {
    setBusy(kind); setNotice("");
    try {
      if (kind === "all") {
        const result = await endpoints.scanAll();
        setNotice(`Scanned ${result.total_devices} devices: ${result.online} online, ${result.offline} offline.`);
        await reload();
      } else {
        const result = await endpoints.scanRange(network);
        setRange(result);
        setNotice(`Range scan completed with ${result.length} host results.`);
      }
    } catch (e) { setNotice(e instanceof Error ? e.message : "Scan failed"); }
    finally { setBusy(""); }
  };
  const live = (event: LiveEvent) => { if (event.event === "device_status_changed") void reload(); };
  const results: Array<RangeResult | Scan> = range ?? data ?? [];

  return <DashboardLayout onLiveEvent={live}>
    <PageTitle eyebrow="Live infrastructure" title="Network monitor" copy="Run approved read-only checks and inspect recent reachability results." action={<button className="primary-action" disabled={!!busy} onClick={() => void run("all")}><Icon name="network"/>{busy === "all" ? "Scanning…" : "Scan all devices"}</button>}/>
    {notice && <div className="inline-notice">{notice}</div>}
    <section className="network-kpis">
      <article><Icon name="check"/><strong>{summary.online}</strong><span>Online checks</span></article>
      <article><Icon name="warning"/><strong>{summary.offline}</strong><span>Offline checks</span></article>
      <form onSubmit={(e: FormEvent) => { e.preventDefault(); void run("range"); }}><label>Approved CIDR range<input value={network} onChange={e => setNetwork(e.target.value)} required/></label><button className="secondary-action" disabled={!!busy}>{busy === "range" ? "Scanning range…" : "Scan range"}</button></form>
    </section>
    <section className="panel">
      <header className="section-head"><div><h2>{range ? "Range scan results" : "Recent device checks"}</h2><p>Latency is reported in milliseconds when the host responds.</p></div>{range && <button className="secondary-action" onClick={() => setRange(null)}>Show history</button>}</header>
      {(loading && !range) || (error && !range) || !results.length ? <Feedback loading={loading && !range} error={!range ? error : ""} empty="No scan results have been recorded." onRetry={reload}/> : <div className="compact-list">{results.slice(0, 100).map((scan, i) => <div key={`${scan.ip_address}-${i}`}><span className={`pulse ${scan.status.toLowerCase()}`}/><strong>{scan.ip_address}</strong><b className={`status-badge ${scan.status.toLowerCase()}`}>{scan.status}</b><span>{scan.response_time == null ? "No response" : `${scan.response_time} ms`}</span></div>)}</div>}
    </section>
  </DashboardLayout>;
}
