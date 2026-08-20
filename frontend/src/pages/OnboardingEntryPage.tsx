import { Link } from "react-router-dom";
import { useState } from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import { Icon } from "../components/Icon";
import { Feedback } from "../components/Feedback";
import { useRequest } from "../hooks/useRequest";
import { endpoints } from "../lib/api";
import { getAuthToken } from "../lib/auth";

type ProgressData = {
  state: string;
  checklist: {
    organization_configured: boolean;
    departments_configured: boolean;
    locations_configured: boolean;
    agent_connected: boolean;
    network_configured: boolean;
    discovery_run: boolean;
    devices_reviewed: boolean;
    devices_approved: boolean;
    monitoring_configured: boolean;
  };
  current_step: string;
  progress_percentage: number;
  steps_completed: number;
  total_steps: number;
  started_at: string | null;
  completed_at: string | null;
};

const steps: { key: keyof ProgressData["checklist"]; label: string; link: string }[] = [
  { key: "organization_configured", label: "Organization configured", link: "/organization-structure" },
  { key: "departments_configured", label: "Departments configured", link: "/organization-structure" },
  { key: "locations_configured", label: "Locations configured", link: "/organization-structure" },
  { key: "agent_connected", label: "Connect local agent", link: "/local-agents" },
  { key: "network_configured", label: "Configure network", link: "/network" },
  { key: "discovery_run", label: "Run first discovery", link: "/discovery-intelligence" },
  { key: "devices_reviewed", label: "Review discovered devices", link: "/devices" },
  { key: "devices_approved", label: "Approve first devices", link: "/devices" },
  { key: "monitoring_configured", label: "Configure monitoring", link: "/integrations" },
];

export default function OnboardingEntryPage() {
  const progress = useRequest<ProgressData>(endpoints.onboardingProgress, []);
  const [isSkipping, setIsSkipping] = useState(false);

  let context: { organization?: { name: string }; property?: { name: string } } = {};
  try {
    context = JSON.parse(window.sessionStorage.getItem("hiop.onboarding") || "{}");
  } catch {
    /* use fallback */
  }

  const completedCount = progress.data
    ? steps.filter((s) => progress.data!.checklist[s.key]).length
    : 0;

  const isComplete = progress.data?.state === "completed" || progress.data?.state === "skipped";

  const handleSkip = async () => {
    setIsSkipping(true);
    try {
      const response = await fetch("/api/v1/onboarding/skip", { 
        method: "POST",
        headers: {
          "Authorization": `Bearer ${getAuthToken()}`,
          "Content-Type": "application/json"
        }
      });
      if (response.ok) {
        window.location.href = "/dashboard";
      } else {
        console.error("Failed to skip onboarding:", response.status);
        setIsSkipping(false);
      }
    } catch (error) {
      console.error("Failed to skip onboarding:", error);
      setIsSkipping(false);
    }
  };

  // Simple fallback if API fails
  if (progress.error) {
    return (
      <DashboardLayout>
        <section className="first-run">
          <p className="page-kicker">Workspace ready</p>
          <h1>Welcome to HIOP</h1>
          <p>Your isolated organization workspace is ready. You can configure it later.</p>
          <div className="first-run-actions">
            <button 
              className="secondary-action" 
              onClick={handleSkip}
              disabled={isSkipping}
            >
              {isSkipping ? "Skipping..." : "Skip for now"}
            </button>
          </div>
        </section>
      </DashboardLayout>
    );
  }

  if (progress.loading) {
    return (
      <DashboardLayout>
        <section className="first-run">
          <Feedback loading={true} />
        </section>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <section className="first-run">
        <p className="page-kicker">{isComplete ? "Setup complete" : "Workspace ready"}</p>
        <h1>{isComplete ? "HIOP is ready" : "Welcome to HIOP"}</h1>
        <p>
          {isComplete
            ? "Your HIOP workspace is fully configured. Start managing your IT infrastructure."
            : "Your isolated organization workspace is ready. Complete the setup steps below to get started with discovery and monitoring."}
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
              {completedCount} / {steps.length} complete ({Math.round(progress.data.progress_percentage)}%)
            </small>
          )}
        </h2>

        {progress.loading || progress.error ? (
          <Feedback loading={progress.loading} error={progress.error} />
        ) : (
          <>
            <ol>
              {steps.map((step) => {
                const done = progress.data?.checklist[step.key] ?? false;
                return (
                  <li className={done ? "done" : ""} key={step.key}>
                    {done ? <Icon name="check" /> : <span />}
                    <Link to={step.link} style={{ color: "inherit", textDecoration: "none" }}>
                      {step.label}
                    </Link>
                  </li>
                );
              })}
            </ol>
            <p style={{ marginTop: "1rem", color: "var(--text-muted)", fontSize: "0.85rem" }}>
              Click any step to configure it, or skip to complete setup later.
            </p>
          </>
        )}

        <div className="first-run-actions">
          {isComplete ? (
            <Link className="primary-action" to="/dashboard">
              Go to HIOP
            </Link>
          ) : (
            <>
              <Link className="primary-action" to="/local-agents">
                Connect agent
              </Link>
              <button 
                className="secondary-action" 
                onClick={handleSkip}
                disabled={isSkipping}
              >
                {isSkipping ? "Skipping..." : "Skip for now"}
              </button>
            </>
          )}
        </div>
      </section>
    </DashboardLayout>
  );
}
