import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { Feedback } from "../components/Feedback";
import { StatCard } from "../components/StatCard";
import { endpoints } from "../lib/api";
import type { Organization, Property } from "../lib/types";
import "../styles/hospitality.css";

export default function HospitalityPage() {
  const location = useLocation();
  const tab = location.pathname.includes("/properties") ? "properties" : "organizations";
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [properties, setProperties] = useState<Property[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [role, setRole] = useState("");
  const admin = role === "admin";
  const load = async () => {
    try { setError(""); const [orgs, sites] = await Promise.all([endpoints.organizations(), endpoints.properties()]); setOrganizations(orgs.items); setProperties(sites.items); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to load hospitality context"); }
  };
  useEffect(() => { queueMicrotask(() => { void load(); void endpoints.me().then(user => setRole(user.role)).catch(() => setRole("")); }); }, []);
  const createOrganization = async () => { if (!admin) return; const name = window.prompt("Organization name"); if (!name) return; const code = window.prompt("Organization code", name.toUpperCase().replaceAll(" ", "-")); if (!code) return; setBusy(true); try { await endpoints.createOrganization({name, code}); await load(); } catch (e) { setError(e instanceof Error ? e.message : "Unable to create organization"); } finally { setBusy(false); } };
  const createProperty = async () => { if (!admin) return; const name = window.prompt("Property name"); if (!name) return; const code = window.prompt("Property code", name.toUpperCase().replaceAll(" ", "-")); setBusy(true); try { await endpoints.createProperty({name, code: code || null, type:"hotel", operational_status:"active"}); await load(); } catch (e) { setError(e instanceof Error ? e.message : "Unable to create property"); } finally { setBusy(false); } };
  return <DashboardLayout><header className="page-title"><div><span className="eyebrow">HIOP v3 foundation</span><h1>{tab === "properties" ? "Properties" : "Organizations"}</h1><p>Hospitality context for existing departments, rooms, devices, and operations.</p></div></header>
    <nav className="hospitality-tabs" aria-label="Hospitality foundation sections"><NavLink to="/organizations" className={tab === "organizations" ? "active" : ""}>Organizations</NavLink><NavLink to="/properties" className={tab === "properties" ? "active" : ""}>Properties</NavLink></nav>
    {error && <Feedback error={error} onRetry={load} />}
    <section className="stats-grid hospitality-stats"><StatCard label="Organizations" value={organizations.length} detail="Configured hospitality groups" icon="users"/><StatCard label="Properties" value={properties.length} detail="Existing and new sites" icon="hierarchy"/><StatCard label="Active properties" value={properties.filter(item => item.operational_status === "active").length} detail="Operational context" icon="check"/></section>
    <section className="hospitality-panel"><div className="panel-heading"><div><h2>{tab === "properties" ? "Property directory" : "Organization directory"}</h2><span>Role-controlled management; existing hierarchy routes remain compatible.</span></div>{admin && <button className="primary-action" disabled={busy} onClick={() => void (tab === "properties" ? createProperty() : createOrganization())}>Add {tab === "properties" ? "property" : "organization"}</button>}</div>
      {tab === "organizations" ? <div className="hospitality-grid">{organizations.map(item => <article className="hospitality-card" key={item.id}><div><strong>{item.name}</strong><span>{item.code} · {item.type.replaceAll("_", " ")}</span></div><b className={`status-badge ${item.status}`}>{item.status}</b><small>{item.country || "Country not set"} · {item.timezone}</small></article>)}{!organizations.length && <Feedback empty="No organizations configured yet."/>}</div> : <div className="hospitality-grid">{properties.map(item => <article className="hospitality-card" key={item.id}><div><strong>{item.name}</strong><span>{item.code || "No code"} · {item.type.replaceAll("_", " ")}</span></div><b className={`status-badge ${item.operational_status}`}>{item.operational_status}</b><small>{[item.city, item.country].filter(Boolean).join(", ") || "Location not set"} · {item.number_of_rooms ?? "—"} rooms</small></article>)}{!properties.length && <Feedback empty="No properties configured yet."/>}</div>}
    </section>
  </DashboardLayout>;
}
