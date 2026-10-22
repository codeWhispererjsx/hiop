import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Feedback } from "../components/Feedback";
import { Icon } from "../components/Icon";
import {
  LocationStep,
  MappingStep,
  MatchReviewStep,
  ReadyStep,
  SummaryStep,
  UploadStep,
  ValidationStep,
  WorksheetStep,
} from "../components/imports/ImportSteps";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import type { ImportColumnDetection, ImportPreview, ImportSession } from "../lib/types";
import { PageTitle } from "./DashboardPage";
import "../styles/inventory-imports.css";

const steps = [
  "Upload",
  "Worksheet",
  "Map columns",
  "Validate",
  "Match",
  "Locations",
  "Conflicts",
  "Summary",
  "Finalize",
];

export default function InventoryImportsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [session, setSession] = useState<ImportSession>();
  const [preview, setPreview] = useState<ImportPreview>();
  const [columns, setColumns] = useState<ImportColumnDetection>();
  const [worksheet, setWorksheet] = useState("");
  const [activeStep, setActiveStep] = useState(0);
  const [error, setError] = useState("");
  const selectedId = searchParams.get("session");
  const activeSession = session?.id === selectedId ? session : undefined;
  const me = useRequest(endpoints.me, []);
  const sessions = useRequest(() => endpoints.importSessions({ page: 1, page_size: 50 }), []);
  const admin = me.data?.role === "admin";

  useEffect(() => {
    if (!selectedId) return;
    let current = true;
    void Promise.all([endpoints.importSession(selectedId), endpoints.importColumns(selectedId)])
      .then(([nextSession, nextColumns]) => {
        if (!current) return;
        setSession(nextSession);
        setColumns(nextColumns);
        setPreview(nextColumns.preview);
        setWorksheet(nextColumns.selected_worksheet ?? "");
        setActiveStep(
          nextSession.status === "uploaded" ? 1
            : nextSession.matching_state === "completed" ? 5
              : nextSession.status === "completed" || nextSession.status === "partial" ? 4
                : 8,
        );
      })
      .catch((reason: unknown) => {
        if (current) setError(reason instanceof Error ? reason.message : "The import session could not be loaded.");
      });
    return () => { current = false; };
  }, [selectedId]);

  const selectSession = (id?: string) => {
    setError("");
    if (!id) {
      setSession(undefined);
      setPreview(undefined);
      setColumns(undefined);
      setWorksheet("");
      setActiveStep(0);
    }
    setSearchParams(id ? { session: id } : {});
  };
  const refreshSession = async () => {
    if (!activeSession) return;
    const result = await endpoints.importSession(activeSession.id);
    setSession(result);
    await sessions.reload();
  };
  const selectWorksheet = async (value: string) => {
    if (!activeSession) return;
    setWorksheet(value);
    setError("");
    try {
      const result = await endpoints.importColumns(activeSession.id, value);
      setColumns(result);
      setPreview(result.preview);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The selected worksheet could not be read.");
    }
  };
  const uploaded = (next: ImportSession, firstPreview: ImportPreview) => {
    setSession(next);
    setPreview(firstPreview);
    setColumns({
      headers: firstPreview.detected_headers,
      suggested_mapping: firstPreview.suggested_mapping,
      mapping: firstPreview.suggested_mapping,
      worksheet_names: firstPreview.worksheet_names,
      selected_worksheet: firstPreview.selected_worksheet,
      unknown_columns: firstPreview.unknown_columns,
      missing_required_columns: firstPreview.missing_required_columns,
      ambiguous_mappings: firstPreview.ambiguous_mappings,
      preview: firstPreview,
    });
    setWorksheet(firstPreview.selected_worksheet ?? "");
    setActiveStep(1);
    setSearchParams({ session: next.id });
    void sessions.reload();
  };
  const afterValidation = (next: ImportSession) => {
    setSession(next);
    setActiveStep(4);
    void sessions.reload();
  };

  return (
    <DashboardLayout>
      <PageTitle
        eyebrow="Inventory management"
        title="Inventory imports"
        copy="Stage, validate, match, and review inventory records before any approved changes are applied."
        action={activeSession ? <button className="secondary-action" onClick={() => selectSession()}>All imports</button> : undefined}
      />
      {error && <div className="inline-notice error" role="alert">{error}</div>}
      {!activeSession ? (
        <div className="inventory-import-layout">
          <div>
            {admin ? (
              <UploadStep admin onUploaded={uploaded} />
            ) : (
              <section className="wizard-card"><div className="inline-notice warning">Inventory uploads and final changes are restricted to organization administrators.</div></section>
            )}
          </div>
          <section className="wizard-card import-history">
            <header><div><h2>Recent import sessions</h2><p>Resume review or inspect the status of earlier uploads.</p></div><button className="secondary-action" onClick={() => void sessions.reload()}>Refresh</button></header>
            {sessions.loading || sessions.error ? (
              <Feedback loading={sessions.loading} error={sessions.error} onRetry={sessions.reload}/>
            ) : !sessions.data?.items.length ? (
              <Feedback emptyTitle="No import sessions" empty="Upload a CSV, Excel workbook, or Word inventory table to start."/>
            ) : (
              <div className="import-session-list">{sessions.data.items.map(item => (
                <button key={item.id} className="import-session-row" onClick={() => selectSession(item.id)}>
                  <span className="import-file-icon"><Icon name="import"/></span>
                  <span className="import-session-name"><strong>{item.original_filename}</strong><small>{item.total_rows} rows · {item.file_format.toUpperCase()} · {new Date(item.uploaded_at).toLocaleString()}</small></span>
                  <span className={`import-state state-${item.status}`}>{item.status.replaceAll("_", " ")}</span>
                </button>
              ))}</div>
            )}
          </section>
        </div>
      ) : (
        <section className="inventory-import-workflow">
          <div className="import-session-heading">
            <div><span>Import session</span><h2>{activeSession.original_filename}</h2><p>{activeSession.total_rows} rows · {activeSession.file_format.toUpperCase()} · Uploaded {new Date(activeSession.uploaded_at).toLocaleString()}</p></div>
            <span className={`import-state state-${activeSession.status}`}>{activeSession.status.replaceAll("_", " ")}</span>
          </div>
          <nav className="import-step-nav" aria-label="Import workflow steps">
            {steps.map((label, index) => (
              <button key={label} className={activeStep === index ? "active" : ""} aria-current={activeStep === index ? "step" : undefined} onClick={() => setActiveStep(index)}>
                <span>{index + 1}</span>{label}
              </button>
            ))}
          </nav>
          {activeStep === 0 && admin && <UploadStep admin onUploaded={uploaded}/>}
          {activeStep === 1 && columns && <WorksheetStep columns={columns} worksheet={worksheet} onSelect={value => void selectWorksheet(value)} onContinue={() => setActiveStep(2)}/>}
          {activeStep === 2 && columns && <MappingStep sessionId={activeSession.id} columns={columns} worksheet={worksheet} admin={admin} onSaved={value => { setColumns(value); setPreview(value.preview); setActiveStep(3); }}/>}
          {activeStep === 3 && <ValidationStep session={activeSession} admin={admin} onValidated={afterValidation}/>}
          {activeStep === 4 && <MatchReviewStep session={activeSession} admin={admin} onChanged={refreshSession}/>}
          {activeStep === 5 && <LocationStep session={activeSession} admin={admin} onChanged={refreshSession}/>}
          {activeStep === 6 && <MatchReviewStep session={activeSession} admin={admin} conflictsOnly onChanged={refreshSession}/>}
          {activeStep === 7 && <SummaryStep session={activeSession}/>}
          {activeStep === 8 && <ReadyStep session={activeSession} admin={admin}/>}
          {preview && activeStep === 1 && <p className="import-preview-note">{preview.validation_summary.total_rows} source rows detected. Preview is limited to {preview.rows.length} rows.</p>}
        </section>
      )}
    </DashboardLayout>
  );
}
