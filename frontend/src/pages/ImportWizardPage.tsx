import { useCallback, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { Feedback } from "../components/Feedback";
import { UploadStep, WorksheetStep, MappingStep, ValidationStep, MatchReviewStep, LocationStep, SummaryStep, ReadyStep } from "../components/imports/ImportSteps";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import type { ImportColumnDetection, ImportPreview, ImportSession, User } from "../lib/types";
import { PageTitle } from "./DashboardPage";
import "../styles/imports.css";

const STEPS = [
  "upload",
  "worksheet",
  "mapping",
  "validate",
  "match",
  "location",
  "conflicts",
  "summary",
  "ready",
] as const;

type Step = (typeof STEPS)[number];

const stepIndex = (step: Step) => STEPS.indexOf(step);

const routeStep = (pathname: string): Step | null => {
  const segment = pathname.split("/").filter(Boolean).at(-1);
  const aliases: Record<string, Step> = {
    worksheet: "worksheet",
    mapping: "mapping",
    validation: "validate",
    matches: "match",
    locations: "location",
    conflicts: "conflicts",
    summary: "summary",
    ready: "ready",
  };
  return segment ? aliases[segment] ?? null : null;
};

const resumeStep = (session: ImportSession): Step => {
  if (session.status === "uploaded") {
    return session.file_format === "xlsx" && !session.selected_worksheet
      ? "worksheet"
      : "mapping";
  }
  if (session.status === "validating" || session.status === "processing")
    return "validate";
  if (session.matching_state !== "completed") return "match";
  const unresolved = Math.max(
    0,
    (session.match_summary.total_valid_rows ?? session.successful_rows) -
      (session.match_summary.resolved ?? 0),
  );
  if ((session.match_summary.conflicts ?? 0) > 0) return "conflicts";
  if (unresolved > 0) return "match";
  return "summary";
};

const stepPath = (sessionId: string, step: Step) => {
  const paths: Partial<Record<Step, string>> = {
    worksheet: "worksheet",
    mapping: "mapping",
    validate: "validation",
    match: "matches",
    location: "locations",
    conflicts: "conflicts",
    summary: "summary",
    ready: "ready",
  };
  return `/imports/${sessionId}/${paths[step] ?? ""}`.replace(/\/$/, "");
};

export default function ImportWizardPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { sessionId } = useParams<{ sessionId: string }>();
  const isNew = !sessionId;

  const [stepState, setStepState] = useState<Step>(
    isNew ? "upload" : routeStep(location.pathname) ?? "mapping",
  );
  const [session, setSession] = useState<ImportSession | null>(null);
  const [columns, setColumns] = useState<ImportColumnDetection | null>(null);
  const [worksheet, setWorksheet] = useState("");

  const me = useRequest<User>(endpoints.me, []);
  const admin = me.data?.role === "admin";

  const existingSession = useRequest(
    () => (sessionId ? endpoints.importSession(sessionId) : Promise.reject()),
    [sessionId],
  );

  const existingColumns = useRequest(
    () =>
      sessionId
        ? endpoints.importColumns(
            sessionId,
            worksheet || existingSession.data?.selected_worksheet || undefined,
          )
        : Promise.reject(),
    [existingSession.data?.selected_worksheet, sessionId, worksheet],
  );

  const loadedSession = useMemo(() => {
    if (session) return session;
    if (existingSession.data) return existingSession.data;
    return null;
  }, [session, existingSession.data]);

  const loadedColumns = useMemo(() => {
    if (columns) return columns;
    if (existingColumns.data) return existingColumns.data;
    return null;
  }, [columns, existingColumns.data]);

  const currentSession = loadedSession;
  const currentColumns = loadedColumns;
  const step =
    !isNew && currentSession
      ? routeStep(location.pathname) ?? resumeStep(currentSession)
      : stepState;
  const currentWorksheet =
    worksheet || currentSession?.selected_worksheet || "";

  const setStep = useCallback(
    (next: Step) => {
      setStepState(next);
      if (currentSession && next !== "upload") {
        navigate(stepPath(currentSession.id, next), { replace: true });
      }
    },
    [currentSession, navigate],
  );

  const onUploaded = useCallback(
    (newSession: ImportSession, newPreview: ImportPreview) => {
      setSession(newSession);
      setColumns(newPreview);
      setWorksheet(newPreview.selected_worksheet ?? "");
      const next =
        newPreview.detected_file_type === "csv" ? "mapping" : "worksheet";
      setStepState(next);
      navigate(stepPath(newSession.id, next), { replace: true });
    },
    [navigate],
  );

  const onWorksheetContinue = useCallback(() => {
    setStep("mapping");
  }, [setStep]);

  const onMappingSaved = useCallback(
    (detection: ImportColumnDetection) => {
      setColumns(detection);
      setStep("validate");
    },
    [setStep],
  );

  const onValidated = useCallback(
    (updatedSession: ImportSession) => {
      setSession(updatedSession);
      setStep("match");
    },
    [setStep],
  );

  const onMatchChanged = useCallback(async () => {
    if (sessionId) {
      try {
        const updated = await endpoints.importSession(sessionId);
        setSession(updated);
      } catch {
        // session unchanged
      }
    }
  }, [sessionId]);

  const canGoBack = stepIndex(step) > 0;
  const goBack = useCallback(() => {
    const idx = stepIndex(step);
    if (idx > 0) setStep(STEPS[idx - 1]);
  }, [setStep, step]);

  const title = isNew ? "New import" : `Import: ${currentSession?.original_filename ?? sessionId}`;

  return (
    <DashboardLayout>
      <PageTitle
        eyebrow="Inventory onboarding"
        title={title}
        copy="Upload, validate, match, and review existing inventory without changing official Devices."
        action={
          <button className="secondary-action" onClick={() => navigate("/imports")}>
            Back to imports
          </button>
        }
      />
      {step !== "upload" && currentSession && (
        <nav className="wizard-steps" aria-label="Import wizard steps">
          {STEPS.map((s) => {
            const idx = stepIndex(s);
            const current = stepIndex(step);
            const done = idx < current;
            return (
              <button
                key={s}
                className={`wizard-step ${s === step ? "active" : ""} ${done ? "done" : ""}`}
                onClick={() => done && setStep(s)}
                disabled={!done && s !== step}
              >
                <span className="step-indicator">{done ? "✓" : idx + 1}</span>
                <span>{s.charAt(0).toUpperCase() + s.slice(1)}</span>
              </button>
            );
          })}
        </nav>
      )}
      {isNew && step === "upload" && (
        <UploadStep admin={admin} onUploaded={onUploaded} />
      )}
      {step === "worksheet" && currentColumns && (
        <WorksheetStep
          columns={currentColumns}
          worksheet={currentWorksheet}
          onSelect={setWorksheet}
          onContinue={onWorksheetContinue}
        />
      )}
      {step === "mapping" && currentSession && currentColumns && (
        <MappingStep
          sessionId={currentSession.id}
          columns={currentColumns}
          worksheet={currentWorksheet}
          admin={admin}
          onSaved={onMappingSaved}
        />
      )}
      {step === "validate" && currentSession && (
        <ValidationStep
          session={currentSession}
          admin={admin}
          onValidated={onValidated}
        />
      )}
      {step === "match" && currentSession && (
        <MatchReviewStep
          session={currentSession}
          admin={admin}
          onChanged={onMatchChanged}
        />
      )}
      {step === "location" && currentSession && (
        <LocationStep
          session={currentSession}
          admin={admin}
          onChanged={onMatchChanged}
        />
      )}
      {step === "conflicts" && currentSession && (
        <MatchReviewStep
          session={currentSession}
          admin={admin}
          conflictsOnly
          onChanged={onMatchChanged}
        />
      )}
      {step === "summary" && currentSession && (
        <SummaryStep session={currentSession} />
      )}
      {step === "ready" && currentSession && (
        <ReadyStep session={currentSession} />
      )}
      {!isNew && !currentSession && (
        <Feedback
          loading={existingSession.loading}
          error={existingSession.error}
          onRetry={existingSession.reload}
        />
      )}
      {currentSession && step !== "upload" && step !== "ready" && (
        <footer className="wizard-nav-actions">
          {canGoBack && (
            <button className="secondary-action" onClick={goBack}>
              Back
            </button>
          )}
          {step === "validate" && (
            <button
              className="primary-action"
              onClick={() => setStep("match")}
            >
              Continue to matching
            </button>
          )}
          {step === "match" && (
            <button
              className="primary-action"
              onClick={() => setStep("location")}
            >
              Continue to locations
            </button>
          )}
          {step === "location" && (
            <button
              className="primary-action"
              onClick={() => setStep("conflicts")}
            >
              Continue to conflicts
            </button>
          )}
          {step === "conflicts" && (
            <button
              className="primary-action"
              onClick={() => setStep("summary")}
            >
              View summary
            </button>
          )}
          {step === "summary" && (
            <button
              className="primary-action"
              onClick={() => setStep("ready")}
            >
              Final review
            </button>
          )}
        </footer>
      )}
    </DashboardLayout>
  );
}
