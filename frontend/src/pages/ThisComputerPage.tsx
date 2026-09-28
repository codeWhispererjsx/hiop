import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import { PageTitle } from "./DashboardPage";
import { Feedback } from "../components/Feedback";

function status(value: boolean) { return value ? "Ready" : "Needs attention"; }

export default function ThisComputerPage() {
  const me = useRequest(endpoints.me, []);
  const scheduler = useRequest(endpoints.automationSchedulerStatus, []);
  if (me.loading || scheduler.loading) return <DashboardLayout><Feedback loading /></DashboardLayout>;
  const serviceReady = !me.error;
  const schedules = scheduler.data?.enabled_schedules ?? 0;
  return <DashboardLayout>
    <PageTitle eyebrow="Local service" title="This Computer" copy="HIOP runs discovery, monitoring, and its private database on this Windows computer." />
    <section className="this-computer-status" aria-label="HIOP desktop status">
      <article><span>HIOP Desktop</span><strong>{status(serviceReady)}</strong><p>{serviceReady ? `Signed in locally as ${me.data?.username ?? "an HIOP user"}.` : "The local HIOP service is not responding."}</p></article>
      <article><span>Private database</span><strong>{status(serviceReady)}</strong><p>Your hotel operational data stays on this computer.</p></article>
      <article><span>Automation scheduler</span><strong>{status(!scheduler.error)}</strong><p>{scheduler.error ? "Scheduler status could not be read." : `${schedules} enabled schedule${schedules === 1 ? "" : "s"}.`}</p></article>
    </section>
    <section className="this-computer-guide">
      <header><span>Local operation</span><h2>How this installation works</h2></header>
      <ol>
        <li><strong>Discovery</strong><span>Runs from this Windows computer and can use local DNS, ping, and supported network evidence.</span></li>
        <li><strong>Monitoring</strong><span>Uses the local scheduler and stores observations in the private HIOP database.</span></li>
        <li><strong>Configuration</strong><span>Use Settings for backup, restore, integrations, SNMP, and operational configuration.</span></li>
      </ol>
      <p className="this-computer-note">This desktop app is already inside the hotel network. It does not need a separate agent download, connection code, or enrolment process.</p>
    </section>
  </DashboardLayout>;
}
