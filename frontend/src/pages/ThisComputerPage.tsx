import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import { PageTitle } from "./DashboardPage";
import { Feedback } from "../components/Feedback";
const state = (value?: string | null) => value === "running" || value === "healthy" || value === "available" ? "Ready" : value === "disabled" ? "Disabled" : value ? "Needs attention" : "Checking";

export default function ThisComputerPage() {
  const me = useRequest(endpoints.me, []);
  const scheduler = useRequest(endpoints.automationSchedulerStatus, []);

  if (me.loading || scheduler.loading) return <DashboardLayout><Feedback loading /></DashboardLayout>;
  const name = me.data?.username || "This Windows computer";
  return <DashboardLayout>
    <PageTitle eyebrow="Local service" title="This Computer" copy="HIOP runs discovery, monitoring, and its private database on this Windows computer." />
    <section className="operations-guide" aria-label="Local HIOP service status">
      <div><span>HIOP desktop</span><strong>{state(me.error ? "needs attention" : "running")}</strong><p>{me.error ? "The local HIOP service could not be reached. Reopen HIOP Desktop and try again." : `Signed in locally as ${name}.`}</p></div>
      <div><span>Private database</span><strong>{state(me.error ? "needs attention" : "available")}</strong><p>Your hotel’s operational data stays on this computer’s bundled database.</p></div>
      <div><span>Automation scheduler</span><strong>{state(scheduler.data?.scheduler_running ? "running" : scheduler.error ? "needs attention" : "disabled")}</strong><p>{scheduler.data?.scheduler_running ? `${scheduler.data.enabled_schedules} enabled schedule(s).` : "No scheduler activity is running."}</p></div>
    </section>
    <section className="panel admin-roles">
      <header><div><span>Local operation</span><h2>How this installation works</h2><p>This desktop app is already inside the hotel network. It does not need a separate local-agent download, connection code, or enrollment process.</p></div></header>
      <div>
        <article><div><strong>Discovery</strong><span>Runs from this Windows computer and can resolve local DNS, ping, and supported network evidence.</span></div></article>
        <article><div><strong>Monitoring</strong><span>Uses the local scheduler and stores results in the private HIOP database.</span></div></article>
        <article><div><strong>Support information</strong><span>Use Settings for backup, restore, integrations, and detailed operational configuration.</span></div></article>
      </div>
    </section>
  </DashboardLayout>;
}

