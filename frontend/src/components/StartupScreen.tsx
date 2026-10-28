import BrandLogo from "./BrandLogo";

export default function StartupScreen({ error }: { error?: string }) {
  const failed = Boolean(error);

  return (
    <main className={`startup-screen${failed ? " startup-screen--error" : ""}`} role={failed ? "alert" : "status"} aria-live={failed ? "assertive" : "polite"}>
      <div className="startup-glow startup-glow--one" aria-hidden="true" />
      <div className="startup-glow startup-glow--two" aria-hidden="true" />
      <section className="startup-card" aria-labelledby="startup-title">
        <header className="startup-header">
          <BrandLogo className="startup-logo" />
          <span className="startup-edition">OPERATIONS PLATFORM</span>
        </header>

        <div className="startup-visual" aria-hidden="true">
          <div className="startup-orbit startup-orbit--outer">
            <span className="startup-orbit-dot" />
          </div>
          <div className="startup-orbit startup-orbit--inner" />
          <div className="startup-core">
            <span className="startup-core-mark">H</span>
            <span className="startup-core-signal" />
          </div>
          <span className="startup-node startup-node--one" />
          <span className="startup-node startup-node--two" />
          <span className="startup-node startup-node--three" />
        </div>

        <div className="startup-copy">
          <p className="startup-kicker">{failed ? "SECURE SESSION" : "HOSPITALITY IT OPERATIONS"}</p>
          <h1 id="startup-title">
            {failed ? "HIOP could not start securely" : "Bringing your operations into focus"}
          </h1>
          <p className="startup-description">
            {failed
              ? error
              : "Connecting your workspace, property context, and live operations."}
          </p>
        </div>

        {failed ? (
          <button className="startup-retry" onClick={() => window.location.reload()}>
            Reload HIOP
          </button>
        ) : (
          <>
            <div className="startup-steps" aria-hidden="true">
              <span>Discover</span><i /><span>Understand</span><i /><span>Operate</span>
            </div>
            <div className="startup-progress" role="progressbar" aria-label="Starting HIOP">
              <span />
            </div>
            <p className="startup-status">Preparing your workspace<span className="startup-ellipsis" /></p>
          </>
        )}

        <footer className="startup-footer">
          <span className="startup-footer-indicator" aria-hidden="true" />
          Hospitality technology, clearly connected.
        </footer>
      </section>
    </main>
  );
}
