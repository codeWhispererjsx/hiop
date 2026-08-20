import { Link } from "react-router-dom";
import { useState } from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import { getAuthToken } from "../lib/auth";

export default function OnboardingEntryPage() {
  const [isSkipping, setIsSkipping] = useState(false);

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

  return (
    <DashboardLayout>
      <section className="first-run">
        <p className="page-kicker">Workspace ready</p>
        <h1>Welcome to HIOP</h1>
        <p>Your isolated organization workspace is ready. Complete the setup steps below to get started with discovery and monitoring.</p>

        <div className="first-run-context">
          <div>
            <span>Organization</span>
            <strong>Current organization</strong>
          </div>
          <div>
            <span>Property</span>
            <strong>Current property</strong>
          </div>
        </div>

        <h2>HIOP setup</h2>

        <ol>
          <li>Organization configured</li>
          <li>Departments configured</li>
          <li>Locations configured</li>
          <li>Connect local agent</li>
          <li>Configure network</li>
          <li>Run first discovery</li>
          <li>Review discovered devices</li>
          <li>Approve first devices</li>
          <li>Configure monitoring</li>
        </ol>

        <p style={{ marginTop: "1rem", color: "var(--text-muted)", fontSize: "0.85rem" }}>
          Click any step to configure it, or skip to complete setup later.
        </p>

        <div className="first-run-actions">
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
        </div>
      </section>
    </DashboardLayout>
  );
}