import { Link } from "react-router-dom";
import BrandLogo from "../components/BrandLogo";
import { Feedback } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { PlatformBilling } from "../components/PlatformBilling";
import { useRequest } from "../hooks/useRequest";
import { endpoints } from "../lib/api";
import "../styles/platform-control.css";

export default function PlatformBillingPage() {
  const billing = useRequest(endpoints.platformBillingOverview, []);

  return (
    <div className="platform-shell">
      <aside className="platform-sidebar">
        <div className="platform-brand">
          <BrandLogo compact />
          <span>Control Center</span>
        </div>
        <p>HIOP OWNER ADMINISTRATION</p>
        <nav aria-label="Platform navigation">
          <Link className="nav-link" to="/platform">
            <Icon name="dashboard" />
            <span>Platform control</span>
          </Link>
          <Link className="nav-link active" to="/platform/billing" aria-current="page">
            <Icon name="audit" />
            <span>Billing readiness</span>
          </Link>
        </nav>
      </aside>
      <main className="platform-main">
        <div className="platform-context-banner">
          <Icon name="lock" />
          <div>
            <strong>HIOP Platform</strong>
            <span>Platform-wide administrative context</span>
          </div>
        </div>
        <header>
          <div>
            <span>HIOP OWNER CONSOLE</span>
            <h1>Billing readiness</h1>
            <p>
              Review organization subscription status. Payment provider processing
              remains disabled until commercial launch.
            </p>
          </div>
        </header>
        {billing.loading || billing.error ? (
          <Feedback loading={billing.loading} error={billing.error} />
        ) : (
          <PlatformBilling data={billing.data} />
        )}
      </main>
    </div>
  );
}