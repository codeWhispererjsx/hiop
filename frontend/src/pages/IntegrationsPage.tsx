import { Link } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { PageTitle } from "./DashboardPage";

export default function IntegrationsPage() {
  return <DashboardLayout>
    <PageTitle eyebrow="Administration" title="Integrations" copy="Manage the external services HIOP currently supports." />
    <section className="panel admin-entry">
      <div><h2>Active Directory</h2><p>Configure optional, read-only directory enrichment for authorized Windows device records.</p></div>
      <Link className="secondary-action" to="/settings">Open integration settings</Link>
    </section>
    <section className="panel admin-entry">
      <div><h2>Email delivery</h2><p>Configure email notifications and daily audit delivery from the Notifications settings.</p></div>
      <Link className="secondary-action" to="/settings">Open notification settings</Link>
    </section>
  </DashboardLayout>;
}
