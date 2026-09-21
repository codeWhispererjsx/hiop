import {Link, useSearchParams} from "react-router-dom";
import {PublicLayout} from "../components/PublicLayout";

const installerUrl="https://github.com/codeWhispererjsx/hiop/releases/download/v0.1.0/HIOP-Desktop-0.1.0-x64.exe";

export default function GetStartedPage(){
 const [params]=useSearchParams();
 const selectedPlan=params.get("plan");
 const demo=params.get("intent")==="demo";
 return <PublicLayout><section className="onboarding-shell desktop-download-shell"><aside><p className="public-eyebrow">HIOP for Windows</p><h1>{demo?"See HIOP in action.":"Run HIOP inside your property."}</h1><p>HIOP is a Windows desktop application. It runs the operational workspace and local network tools on a computer that can see the property network.</p><ol><li className="active"><span>1</span>Download</li><li className="active"><span>2</span>Install</li><li className="active"><span>3</span>Create your workspace</li></ol>{selectedPlan&&<small>Selected plan: {selectedPlan}. Plans are confirmed by the Platform Control Center when commercial onboarding begins.</small>}</aside><div className="onboarding-card desktop-download-card"><p className="public-eyebrow">Desktop application</p><h2>Download HIOP Desktop</h2><p>Install this on a Windows computer at the hotel or office. The first launch guides you through creating the Platform Owner, organisation, first property, and administrator account.</p><a className="public-button" href={installerUrl}>Download for Windows</a><p className="onboarding-note">Windows may ask for permission before installation. Choose a computer that stays available for monitoring and network discovery.</p><div className="onboarding-actions"><Link to="/features">Explore features</Link><Link to="/pricing">View plans</Link></div></div></section></PublicLayout>
}
