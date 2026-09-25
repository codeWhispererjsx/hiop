import {Link} from "react-router-dom";
import {PublicLayout} from "../components/PublicLayout";

const installerUrl="https://github.com/codeWhispererjsx/hiop/releases/download/v2.0.0/HIOP-Desktop-2.0.0-x64.exe";

export default function GetStartedPage(){
  return <PublicLayout>
    <section className="onboarding-shell desktop-download-shell">
      <aside className="desktop-download-intro">
        <p className="public-eyebrow">HIOP for Windows</p>
        <h1>Run HIOP where your network lives.</h1>
        <p>HIOP is a Windows desktop application for hotel and property IT teams. It keeps discovery, monitoring, assets, and operations close to the network.</p>
        <ol>
          <li className="active"><span>1</span><div><strong>Download</strong><small>Get the Windows installer.</small></div></li>
          <li className="active"><span>2</span><div><strong>Install</strong><small>Use a computer that can see the property network.</small></div></li>
          <li className="active"><span>3</span><div><strong>Create your workspace</strong><small>Set up your Platform Owner, organisation, property, and administrator.</small></div></li>
        </ol>
      </aside>

      <div className="onboarding-card desktop-download-card">
        <div className="desktop-download-card-head">
          <span className="desktop-download-icon">â†“</span>
          <div><p className="public-eyebrow">Desktop application</p><h2>Download HIOP Desktop</h2></div>
        </div>
        <p className="desktop-download-copy">Install HIOP on a Windows computer at the hotel or office. Your data and operational tools run locally on that computer.</p>
        <div className="desktop-download-meta"><span>Windows 10 or later</span><span>Local database included</span><span>Version 2.0</span></div>
        <a className="public-button desktop-download-button" href={installerUrl}>Download for Windows <span aria-hidden="true">â†’</span></a>
        <p className="onboarding-note">Windows may ask for permission before installation. Choose a computer that stays available for monitoring and network discovery.</p>
        <div className="desktop-download-links"><Link to="/features">Explore features</Link></div>
      </div>
    </section>
  </PublicLayout>;
}
