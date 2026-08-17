import { Link } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { Icon } from "../components/Icon";
import { Feedback } from "../components/Feedback";
import { useRequest } from "../hooks/useRequest";
import { endpoints } from "../lib/api";

type ProgressData = {
  organization_created: boolean;
  property_created: boolean;
  discovery_configured: boolean;
  agent_connected: boolean;
  scan_run: boolean;
  devices_approved: boolean;
  monitoring_configured: boolean;
};

const steps: { key: keyof ProgressData; label: string }[] = [
  { key: "organization_created", label: "Organization created" },
  { key: "property_created", label: "Property created" },
  { key: "discovery_configured", label: "Configure discovery" },
  { key: "agent_connected", label: "Connect local agent" },
  { key: "scan_run", label: "Run first scan" },
  { key: "devices_approved", label: "Approve first devices" },
  { key: "monitoring_configured", label: "Configure monitoring" },
];

export default function OnboardingEntryPage() {
  const progress = useRequest<ProgressData>(endpoints.onboardingProgress, []);

  let context: { organization?: { name: string }; property?: { name: string } } = {};
  try {
    context = JSON.parse(window.sessionStorage.getItem("hiop.onboarding") || "{}");
  } catch {
    /* use fallback */
  }

  const completedCount = progress.data
    ? steps.filter((s) => progress.data![s.key]).length
    : 0;

  return (
    <DashboardLayout>
      <section className="first-run">
        <p className="page-kicker">Workspace ready</p>
        <h1>Welcome to HIOP</h1>
        <p>
          Your isolated organization workspace is ready. Start with discovery when
          your property network is prepared.
        </p>

        <div className="first-run-context">
          <div>
            <span>Organization</span>
            <strong>{context.organization?.name || "Current organization"}</strong>
          </div>
          <div>
            <span>Property</span>
            <strong>{context.property?.name || "Current property"}</strong>
          </div>
        </div>

        <h2>
          HIOP setup{" "}
          {progress.data && (
            <small style={{ fontWeight: 400, fontSize: ".85rem", color: "var(--text-muted)" }}>
              {completedCount} / {steps.length} complete
            </small>
          )}
        </h2>

        {progress.loading || progress.error ? (
          <Feedback loading={progress.loading} error={progress.error} />
        ) : (
          <ol>
            {steps.map((step) => {
              const done = progress.data?.[step.key] ?? false;
              return (
                <li className={done ? "done" : ""} key={step.key}>
                  {done ? <Icon name="check" /> : <span />}
                  {step.label}
                </li>
              );
            })}
          </ol>
        )}

        <div className="first-run-actions">
          <Link className="primary-action" to="/discovery-intelligence">
            Configure discovery
          </Link>
          <Link className="secondary-action" to="/dashboard">
            Open dashboard
          </Link>
        </div>
      </section>
    </DashboardLayout>
  );
}
