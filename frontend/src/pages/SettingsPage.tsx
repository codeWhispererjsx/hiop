/* eslint-disable react-hooks/set-state-in-effect */
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { PageTitle } from "./DashboardPage";
import { Feedback } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { Toast } from "../components/Toast";
import { endpoints } from "../lib/api";
import { LANDING_PAGES, resolveLandingPage } from "../lib/landingPage";
import type { OrganizationDepartment, OrganizationLocation, SettingsBundle, SystemHealth } from "../lib/types";
import { useTheme, type ThemePreference } from "../theme/ThemeContext";
import { ActiveDirectorySettings } from "../components/ActiveDirectorySettings";

type Section =
  | "general"
  | "organization"
  | "departments"
  | "locations"
  | "naming_convention"
  | "network"
  | "discovery"
  | "active_directory"
  | "notifications"
  | "incidents"
  | "appearance"
  | "security"
  | "health"
  | "maintenance"
  | "about";

const sections: Array<{
  key: Section;
  label: string;
  icon: "settings" | "hierarchy" | "network" | "discovery" | "bell" | "sun" | "lock" | "server" | "audit";
}> = [
  { key: "general", label: "General", icon: "settings" },
  { key: "organization", label: "Organization", icon: "hierarchy" },
  { key: "departments", label: "Departments", icon: "hierarchy" },
  { key: "locations", label: "Locations", icon: "hierarchy" },
  { key: "naming_convention", label: "Naming Convention", icon: "settings" },
  { key: "network", label: "Network & scanner", icon: "network" },
  { key: "discovery", label: "Discovery", icon: "discovery" },
  { key: "active_directory", label: "Active Directory", icon: "lock" },
  { key: "notifications", label: "Notifications & email", icon: "bell" },
  { key: "incidents", label: "Incident management", icon: "audit" },
  { key: "appearance", label: "Appearance", icon: "sun" },
  { key: "security", label: "Security", icon: "lock" },
  { key: "health", label: "System health", icon: "server" },
  { key: "maintenance", label: "Backup & maintenance", icon: "audit" },
  { key: "about", label: "Application information", icon: "settings" },
];

const NAMING_VARIABLES = [
  { token: "COMPANY", label: "Company" },
  { token: "LOCATION", label: "Location" },
  { token: "FLOOR", label: "Floor" },
  { token: "BUILDING", label: "Building" },
  { token: "DEPT", label: "Department" },
  { token: "TYPE", label: "Type" },
  { token: "USER", label: "User" },
  { token: "NUM", label: "Number" },
  { token: "NUM:02", label: "Number (2 digits)" },
  { token: "NUM:03", label: "Number (3 digits)" },
  { token: "NUM:04", label: "Number (4 digits)" },
  { token: "NUM:05", label: "Number (5 digits)" },
  { token: "NUM:06", label: "Number (6 digits)" },
  { token: "YEAR", label: "Year" },
  { token: "ASSET", label: "Asset name" },
];

function previewNamingTemplate(template: string): string {
  const examples: Record<string, string> = {
    COMPANY: "LCH",
    LOCATION: "03",
    FLOOR: "03",
    BUILDING: "MAIN",
    DEPT: "ACC",
    TYPE: "DT",
    USER: "JSMITH",
    YEAR: "2026",
    ASSET: "DESKTOP",
  };
  return template.replace(/\{([A-Z]+(?::\d{2})?)\}/g, (_match, token: string) => {
    if (token.startsWith("NUM")) {
      const width = Number(token.split(":")[1] ?? 0);
      return String(5).padStart(width, "0");
    }
    return examples[token] ?? `{${token}}`;
  });
}

function namingTokens(template: string): string[] {
  return Array.from(template.matchAll(/\{([^{}]+)\}/g), (match) => match[1]);
}

function templateWithOrderedTokens(template: string, tokens: string[], separator: string): string {
  const matches = Array.from(template.matchAll(/\{[^{}]+\}/g));
  if (!matches.length) return tokens.map((token) => `{${token}}`).join(separator);
  const prefix = template.slice(0, matches[0].index);
  const suffix = template.slice(matches[matches.length - 1].index! + matches[matches.length - 1][0].length);
  return `${prefix}${tokens.map((token) => `{${token}}`).join(separator)}${suffix}`;
}

function removeNamingToken(template: string, tokenIndex: number): string {
  const matches = Array.from(template.matchAll(/\{[^{}]+\}/g));
  const tokenMatch = matches[tokenIndex];
  if (!tokenMatch || tokenMatch.index === undefined) return template;
  const start = tokenMatch.index;
  const end = start + tokenMatch[0].length;
  const following = template.slice(end).match(/^[._-]*/)?.[0] ?? "";
  const preceding = template.slice(0, start).match(/[._-]*$/)?.[0] ?? "";
  const nextTokenExists = matches.slice(tokenIndex + 1).length > 0;
  if (nextTokenExists && following) return `${template.slice(0, start)}${template.slice(end + following.length)}`;
  if (preceding) return `${template.slice(0, start - preceding.length)}${template.slice(end)}`;
  if (following) return `${template.slice(0, start)}${template.slice(end + following.length)}`;
  return `${template.slice(0, start)}${template.slice(end)}`;
}

export default function SettingsPage() {
  const [section, setSection] = useState<Section>("general");
  const [draft, setDraft] = useState<SettingsBundle | null>(null);
  const [departments,setDepartments]=useState<OrganizationDepartment[]>([]);
  const [locations,setLocations]=useState<OrganizationLocation[]>([]);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [draggingNamingToken, setDraggingNamingToken] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const { preference, setPreference } = useTheme();

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const settings = await endpoints.settings();
      setDraft(settings);
      try {
        const [d,l]=await Promise.all([endpoints.organizationDepartments(),endpoints.organizationLocations()]);setDepartments(d);setLocations(l);
      } catch {
        setDepartments([]);setLocations([]);
        setNotice("Core settings loaded. Location hierarchy is temporarily unavailable.");
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Settings could not be loaded.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    let active = true;
    const refreshHierarchy = async () => {
      try {
        const [nextDepartments, nextLocations] = await Promise.all([
          endpoints.organizationDepartments(),
          endpoints.organizationLocations(),
        ]);
        if (active) {
          setDepartments(nextDepartments);
          setLocations(nextLocations);
        }
      } catch (caught) {
        if (active) {
          setNotice(caught instanceof Error ? caught.message : "Departments and locations could not be refreshed.");
        }
      }
    };
    window.addEventListener("hiop:organization-updated", refreshHierarchy);
    return () => {
      active = false;
      window.removeEventListener("hiop:organization-updated", refreshHierarchy);
    };
  }, []);

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    setNotice("");
    try {
      let result = draft;
      if (section === "general") {
        result = await endpoints.updateGeneralSettings(draft.general);
      } else if (section === "organization") {
        result = await endpoints.updateOrganizationSettings(draft.organization);
        window.dispatchEvent(new Event("hiop:organization-updated"));
      } else if (section === "network") {
        result = await endpoints.updateNetworkSettings(draft.network);
      } else if (section === "discovery") {
        result = await endpoints.updateDiscoverySettings(draft.discovery);
      } else if (section === "notifications") {
        result = await endpoints.updateNotificationSettings(draft.notifications);
      } else if (section === "incidents") {
        result = await endpoints.updateIncidentSettings(draft.incidents);
      } else if (section === "naming_convention") {
        result = await endpoints.updateNamingConventionSettings(draft.naming_convention);
      }
      setDraft(result);
      window.dispatchEvent(new Event("hiop:organization-updated"));
      setNotice(`${sections.find((item) => item.key === section)?.label} settings saved.`);
    } catch (caught) {
      setNotice(caught instanceof Error ? caught.message : "Settings could not be saved.");
    } finally {
      setSaving(false);
    }
  };

  const refreshHealth = async () => {
    setHealth(null);
    try {
      setHealth(await endpoints.systemHealth());
    } catch (caught) {
      setNotice(caught instanceof Error ? caught.message : "Health check failed.");
    }
  };

  useEffect(() => {
    if (section === "health" && !health) void refreshHealth();
  }, [section, health]);

  if (loading || error || !draft) {
    return (
      <DashboardLayout>
        <PageTitle
          eyebrow="Administration"
          title="Settings"
          copy="Secure global configuration and operational health."
        />
        <Feedback loading={loading} error={error || undefined} onRetry={() => void load()} />
      </DashboardLayout>
    );
  }

  const g = draft.general;

  const n = draft.network;
  const d = draft.discovery;
  const notifications = draft.notifications;
  const incidents = draft.incidents;
  const namingConvention = draft.naming_convention;
  const currentNamingTokens = namingTokens(namingConvention.template);

  return (
    <DashboardLayout>
      <PageTitle
        eyebrow="Administration"
        title="Settings & administration"
        copy="Manage safe runtime configuration, organizational structure, appearance and system health."
      />
      {notice && (
        <Toast
          message={notice}
          tone={notice.toLowerCase().includes("saved") ? "success" : "error"}
        />
      )}
      <div className="settings-layout">
        <nav className="settings-nav" aria-label="Settings sections">
          {sections.map((item) => (
            <button
              key={item.key}
              className={section === item.key ? "active" : ""}
              onClick={() => setSection(item.key)}
              aria-current={section === item.key ? "page" : undefined}
            >
              <Icon name={item.icon} aria-hidden="true" />
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
        <section className="settings-workspace">
          {section === "general" && (
            <SettingsPanel
              title="General settings"
              copy="Choose time and display preferences for your organisation."
            >
              <div className="settings-form-grid">
                <div><span>Application</span><p><strong>HIOP</strong></p><small>Application name, version, and core identity are platform-owned and read-only.</small></div>
                <Field
                  label="Time zone"
                  value={g.timezone}
                  onChange={(value) =>
                    setDraft({ ...draft, general: { ...g, timezone: value } })
                  }
                />
                <SelectField
                  label="Date format"
                  value={g.date_format}
                  options={["DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD"]}
                  onChange={(value) =>
                    setDraft({
                      ...draft,
                      general: { ...g, date_format: value as typeof g.date_format },
                    })
                  }
                />
                <SelectField
                  label="Time format"
                  value={g.time_format}
                  options={["12-hour", "24-hour"]}
                  onChange={(value) =>
                    setDraft({
                      ...draft,
                      general: { ...g, time_format: value as typeof g.time_format },
                    })
                  }
                />
                <SelectField
                  label="Default page size"
                  value={String(g.default_page_size)}
                  options={["10", "25", "50", "100"]}
                  onChange={(value) =>
                    setDraft({
                      ...draft,
                      general: {
                        ...g,
                        default_page_size: Number(value) as 10 | 25 | 50 | 100,
                      },
                    })
                  }
                />
                <SelectField
                  label="Default landing page"
                  value={resolveLandingPage(g.default_landing_page)}
                  options={LANDING_PAGES}
                  onChange={(value) =>
                    setDraft({ ...draft, general: { ...g, default_landing_page: value } })
                  }
                />
                <Field
                  label="Support email"
                  type="email"
                  value={g.support_email ?? ""}
                  onChange={(value) =>
                    setDraft({
                      ...draft,
                      general: { ...g, support_email: value || null },
                    })
                  }
                />
              </div>
              <SaveButton saving={saving} onClick={save} />
            </SettingsPanel>
          )}

          {section === "organization" && <SettingsPanel title="Organisation details" copy="Manage the shared information used throughout HIOP."><Link className="primary-action" to="/administration/organization">Edit organisation details</Link></SettingsPanel>}
          {section === "departments" && (
            <HierarchySummary
              title="Departments"
              copy="Your organisation’s departments. Changes appear here and on the organisation page."
              items={departments}
              link="/administration/organization?tab=departments"
            />
          )}

          {section === "locations" && (
            <HierarchySummary
              title="Locations"
              copy="Your organisation’s buildings, floors, rooms, and other locations."
              items={locations}
              link="/administration/organization?tab=locations"
            />
          )}

          {section === "naming_convention" && (
            <SettingsPanel
              title="Naming Convention Builder"
              copy="Define the asset number format used for new assets in your organization."
            >
              <div className="settings-form-grid">
                <label>
                  <span>Template</span>
                  <input
                    required
                    maxLength={120}
                    type="text"
                    value={namingConvention.template}
                    onChange={(event) => {
                      const template = event.target.value;
                      const variables = [...new Set(Array.from(template.matchAll(/\{([^{}]+)\}/g), (match) => match[1]))];
                      setDraft({ ...draft, naming_convention: { ...namingConvention, template, variables } });
                    }}
                    aria-label="Asset number template"
                  />
                </label>
                <SelectField
                  label="Separator"
                  value={namingConvention.separator || "(none)"}
                  options={["-", "_", ".", "(none)"]}
                  onChange={(value) => {
                    const separator = value === "(none)" ? "" : value as "-" | "_" | ".";
                    const template = namingConvention.template.replace(/}(?:[-_.]+)(?=\{)/g, `}${separator}`);
                    setDraft({
                      ...draft,
                      naming_convention: { ...namingConvention, template, separator },
                    });
                  }}
                />
              </div>
              <p className="settings-note">Choose “(none)” to concatenate variables directly with no punctuation. Drag variables to reorder them or use the move buttons. Remove variables with Remove; at least one sequential number is required. You can also type or edit the template directly.</p>
              <div className="settings-record-list" aria-label="Reorder or remove naming variables">
                {currentNamingTokens.map((token, index) => {
                  const label = NAMING_VARIABLES.find((item) => item.token === token)?.label ?? token;
                  return (
                    <div
                      key={`${token}-${index}`}
                      draggable
                      onDragStart={(event) => {
                        event.dataTransfer.setData("text/plain", String(index));
                        event.dataTransfer.effectAllowed = "move";
                        setDraggingNamingToken(index);
                      }}
                      onDragOver={(event) => event.preventDefault()}
                      onDrop={(event) => {
                        event.preventDefault();
                        if (draggingNamingToken === null || draggingNamingToken === index) return;
                        const nextTokens = [...currentNamingTokens];
                        const [moved] = nextTokens.splice(draggingNamingToken, 1);
                        nextTokens.splice(index, 0, moved);
                        const template = templateWithOrderedTokens(namingConvention.template, nextTokens, namingConvention.separator);
                        setDraft({
                          ...draft,
                          naming_convention: { ...namingConvention, template, variables: nextTokens },
                        });
                        setDraggingNamingToken(null);
                      }}
                      onDragEnd={() => setDraggingNamingToken(null)}
                    >
                      <span>
                        <i aria-hidden="true">⠿</i>
                        <strong>{label}</strong>
                        <code>{`{${token}}`}</code>
                      </span>
                      <span>
                        <button
                          className="secondary-action"
                          type="button"
                          disabled={index === 0}
                          aria-label={`Move ${label} up`}
                          onClick={() => {
                            const nextTokens = [...currentNamingTokens];
                            [nextTokens[index - 1], nextTokens[index]] = [nextTokens[index], nextTokens[index - 1]];
                            const template = templateWithOrderedTokens(namingConvention.template, nextTokens, namingConvention.separator);
                            setDraft({ ...draft, naming_convention: { ...namingConvention, template, variables: nextTokens } });
                          }}
                        >Up</button>
                        <button
                          className="secondary-action"
                          type="button"
                          disabled={index === currentNamingTokens.length - 1}
                          aria-label={`Move ${label} down`}
                          onClick={() => {
                            const nextTokens = [...currentNamingTokens];
                            [nextTokens[index], nextTokens[index + 1]] = [nextTokens[index + 1], nextTokens[index]];
                            const template = templateWithOrderedTokens(namingConvention.template, nextTokens, namingConvention.separator);
                            setDraft({ ...draft, naming_convention: { ...namingConvention, template, variables: nextTokens } });
                          }}
                        >Down</button>
                        <button
                          className="secondary-action"
                          type="button"
                          aria-label={`Remove ${label}`}
                          disabled={token.startsWith("NUM") && !currentNamingTokens.some((item, itemIndex) => itemIndex !== index && item.startsWith("NUM"))}
                          onClick={() => {
                            const template = removeNamingToken(namingConvention.template, index);
                            const variables = namingTokens(template);
                            setDraft({ ...draft, naming_convention: { ...namingConvention, template, variables } });
                          }}
                        >Remove</button>
                      </span>
                    </div>
                  );
                })}
                {!currentNamingTokens.length && <p>No variables in the template yet. Add one below.</p>}
              </div>
              <div className="module-list" aria-label="Add naming variable">
                <strong>Add variable</strong>
                {NAMING_VARIABLES.map(({ token, label }) => (
                  <button
                    className="secondary-action"
                    key={token}
                    type="button"
                    onClick={() => {
                      const separator = namingConvention.separator;
                      const joiner = namingConvention.template && separator && !namingConvention.template.endsWith(separator) ? separator : "";
                      const template = `${namingConvention.template}${joiner}{${token}}`;
                      const variables = namingTokens(template);
                      setDraft({ ...draft, naming_convention: { ...namingConvention, template, variables } });
                    }}
                  >
                    + {label}
                  </button>
                ))}
              </div>
              <p className="settings-note">
                Supported variables: {NAMING_VARIABLES.map(({ token }) => `{${token}}`).join(", ")}, plus padded numbers such as {"{NUM:02}"} through {"{NUM:06}"}. Include a number variable so generated asset numbers remain unique.
              </p>
              <div className="settings-readonly">
                <div><dt>Live preview</dt><dd><code>{previewNamingTemplate(namingConvention.template)}</code></dd></div>
                <div><dt>Variables in template</dt><dd>{namingConvention.variables.length ? namingConvention.variables.map((variable) => `{${variable}}`).join(", ") : "None"}</dd></div>
              </div>
              <SaveButton saving={saving} onClick={save} />
            </SettingsPanel>
          )}

          {section === "network" && (
            <SettingsPanel
              title="Network & scanner"
              copy="Choose approved networks and scanning preferences."
            >
              <div className="settings-form-grid">
                <Field
                  label="Approved private networks (comma separated)"
                  value={n.approved_network}
                  onChange={(value) =>
                    setDraft({ ...draft, network: { ...n, approved_network: value } })
                  }
                />
                <NumberField
                  label="Scan interval (minutes)"
                  value={n.scan_interval_minutes}
                  min={5}
                  max={1440}
                  onChange={(value) =>
                    setDraft({ ...draft, network: { ...n, scan_interval_minutes: value } })
                  }
                />
                <NumberField
                  label="Ping timeout (seconds)"
                  value={n.ping_timeout_seconds}
                  min={1}
                  max={30}
                  onChange={(value) =>
                    setDraft({ ...draft, network: { ...n, ping_timeout_seconds: value } })
                  }
                />
                <NumberField
                  label="Maximum workers"
                  value={n.max_concurrent_workers}
                  min={1}
                  max={32}
                  onChange={(value) =>
                    setDraft({ ...draft, network: { ...n, max_concurrent_workers: value } })
                  }
                />
                <NumberField
                  label="Offline threshold"
                  value={n.offline_threshold}
                  min={1}
                  max={20}
                  onChange={(value) =>
                    setDraft({ ...draft, network: { ...n, offline_threshold: value } })
                  }
                />
              </div>
              <p className="settings-note">
                <Icon name="lock" aria-hidden="true" />
                Add multiple ranges with commas, for example: 10.50.20.0/24,
                192.168.10.0/24.
              </p>
              <div className="settings-toggles">
                <Toggle
                  label="Automatic scanning"
                  checked={n.automatic_scanning}
                  onChange={(value) =>
                    setDraft({ ...draft, network: { ...n, automatic_scanning: value } })
                  }
                />
                <Toggle
                  label="Exclude retired devices"
                  checked={n.exclude_retired_devices}
                  onChange={(value) =>
                    setDraft({ ...draft, network: { ...n, exclude_retired_devices: value } })
                  }
                />
                <Toggle
                  label="Automatic alerts"
                  checked={n.automatic_alerts}
                  onChange={(value) =>
                    setDraft({ ...draft, network: { ...n, automatic_alerts: value } })
                  }
                />
                <Toggle
                  label="Automatic offline tickets"
                  checked={n.automatic_offline_tickets}
                  onChange={(value) =>
                    setDraft({ ...draft, network: { ...n, automatic_offline_tickets: value } })
                  }
                />
              </div>
              <SaveButton saving={saving} onClick={save} />
            </SettingsPanel>
          )}

          {section === "discovery" && (
            <SettingsPanel
              title="Discovery"
              copy="Conservative private-network discovery. Changes immediately update the single scheduled job."
            >
              <div className="settings-form-grid">
                <Field
                  label="Authorized private CIDRs (comma separated)"
                  value={d.authorized_cidr_ranges}
                  onChange={(value) =>
                    setDraft({ ...draft, discovery: { ...d, authorized_cidr_ranges: value } })
                  }
                />
                <Field
                  label="Ignored private CIDRs"
                  value={d.ignore_ranges}
                  onChange={(value) =>
                    setDraft({ ...draft, discovery: { ...d, ignore_ranges: value } })
                  }
                />
                <NumberField
                  label="Interval (minutes)"
                  value={d.interval_minutes}
                  min={15}
                  max={10080}
                  onChange={(value) =>
                    setDraft({ ...draft, discovery: { ...d, interval_minutes: value } })
                  }
                />
                <NumberField
                  label="Ping timeout (seconds)"
                  value={d.ping_timeout_seconds}
                  min={1}
                  max={10}
                  onChange={(value) =>
                    setDraft({ ...draft, discovery: { ...d, ping_timeout_seconds: value } })
                  }
                />
                <NumberField
                  label="Maximum workers"
                  value={d.concurrency_limit}
                  min={1}
                  max={32}
                  onChange={(value) =>
                    setDraft({ ...draft, discovery: { ...d, concurrency_limit: value } })
                  }
                />
                <NumberField
                  label="Maximum hosts per run"
                  value={d.max_hosts_per_run}
                  min={1}
                  max={4096}
                  onChange={(value) =>
                    setDraft({ ...draft, discovery: { ...d, max_hosts_per_run: value } })
                  }
                />
                <NumberField
                  label="Admin notification threshold"
                  value={d.admin_notification_threshold}
                  min={0}
                  max={4096}
                  onChange={(value) =>
                    setDraft({ ...draft, discovery: { ...d, admin_notification_threshold: value } })
                  }
                />
              </div>
              <div className="settings-toggles">
                <Toggle
                  label="Scheduled discovery"
                  checked={d.enabled}
                  onChange={(value) =>
                    setDraft({ ...draft, discovery: { ...d, enabled: value } })
                  }
                />
                <Toggle
                  label="Vendor lookup"
                  checked={d.automatic_vendor_lookup}
                  onChange={(value) =>
                    setDraft({ ...draft, discovery: { ...d, automatic_vendor_lookup: value } })
                  }
                />
                <Toggle
                  label="Reverse DNS"
                  checked={d.automatic_hostname_lookup}
                  onChange={(value) =>
                    setDraft({ ...draft, discovery: { ...d, automatic_hostname_lookup: value } })
                  }
                />
              </div>
              <p className="settings-note">
                <Icon name="lock" aria-hidden="true" />
                Only authorized private IPv4 ranges are accepted. Discovery uses ICMP,
                the local ARP cache, and safe vendor fingerprinting.
              </p>
              <SaveButton saving={saving} onClick={save} />
            </SettingsPanel>
          )}

          {section === "active_directory" && (
            <SettingsPanel
              title="Active Directory"
              copy="Read-only Windows computer identification through a securely configured LDAP endpoint."
            >
              <ActiveDirectorySettings />
            </SettingsPanel>
          )}

          {section === "notifications" && (
            <SettingsPanel
              title="Notifications & email"
              copy="Choose which events should send an email to your team."
            >
              <div className="settings-toggles">
                <Toggle
                  label="Email notifications"
                  checked={notifications.email_notifications}
                  onChange={(value) =>
                    setDraft({
                      ...draft,
                      notifications: { ...notifications, email_notifications: value },
                    })
                  }
                />
                <Toggle
                  label="Device offline"
                  checked={notifications.device_offline}
                  onChange={(value) =>
                    setDraft({
                      ...draft,
                      notifications: { ...notifications, device_offline: value },
                    })
                  }
                />
                <Toggle
                  label="Device restored"
                  checked={notifications.device_restored}
                  onChange={(value) =>
                    setDraft({
                      ...draft,
                      notifications: { ...notifications, device_restored: value },
                    })
                  }
                />
                <Toggle
                  label="Ticket assignment"
                  checked={notifications.ticket_assignment}
                  onChange={(value) =>
                    setDraft({
                      ...draft,
                      notifications: { ...notifications, ticket_assignment: value },
                    })
                  }
                />
                <Toggle
                  label="Critical alerts"
                  checked={notifications.critical_alerts}
                  onChange={(value) =>
                    setDraft({
                      ...draft,
                      notifications: { ...notifications, critical_alerts: value },
                    })
                  }
                />
              </div>
              <div className="settings-form-grid">
                <Field
                  label="Sender display name"
                  value={notifications.sender_display_name}
                  onChange={(value) =>
                    setDraft({
                      ...draft,
                      notifications: { ...notifications, sender_display_name: value },
                    })
                  }
                />
                <Field
                  label="Recipient email"
                  type="email"
                  value={notifications.recipient_email ?? ""}
                  onChange={(value) =>
                    setDraft({
                      ...draft,
                      notifications: { ...notifications, recipient_email: value || null },
                    })
                  }
                />
              </div>
              <p className="settings-note">{draft.email.configured?"Email delivery is configured.":"Email delivery is not available yet. Contact the platform owner."}</p>
              <SaveButton saving={saving} onClick={save} />
            </SettingsPanel>
          )}

          {section === "incidents" && (
            <SettingsPanel
              title="Incident management"
              copy="Human-controlled incident, playbook, response-target, evidence, and retention safeguards."
            >
              <div className="settings-toggles">
                <Toggle
                  label="Incident management"
                  checked={incidents.enabled}
                  onChange={(value) =>
                    setDraft({ ...draft, incidents: { ...incidents, enabled: value } })
                  }
                />
                <Toggle
                  label="Automatic pending declaration"
                  checked={incidents.automatic_incident_declaration_enabled}
                  onChange={(value) =>
                    setDraft({
                      ...draft,
                      incidents: { ...incidents, automatic_incident_declaration_enabled: value },
                    })
                  }
                />
                <Toggle
                  label="Task escalation"
                  checked={incidents.task_escalation_enabled}
                  onChange={(value) =>
                    setDraft({ ...draft, incidents: { ...incidents, task_escalation_enabled: value } })
                  }
                />
                <Toggle
                  label="Remediation recommendations"
                  checked={incidents.remediation_recommendations_enabled}
                  onChange={(value) =>
                    setDraft({
                      ...draft,
                      incidents: { ...incidents, remediation_recommendations_enabled: value },
                    })
                  }
                />
                <Toggle
                  label="Incident merge"
                  checked={incidents.incident_merge_enabled}
                  onChange={(value) =>
                    setDraft({ ...draft, incidents: { ...incidents, incident_merge_enabled: value } })
                  }
                />
                <Toggle
                  label="Incident reopen"
                  checked={incidents.incident_reopen_enabled}
                  onChange={(value) =>
                    setDraft({ ...draft, incidents: { ...incidents, incident_reopen_enabled: value } })
                  }
                />
              </div>
              <div className="settings-form-grid">
                <NumberField
                  label="Duplicate window (minutes)"
                  value={incidents.duplicate_window_minutes}
                  min={5}
                  max={10080}
                  onChange={(value) =>
                    setDraft({ ...draft, incidents: { ...incidents, duplicate_window_minutes: value } })
                  }
                />
                <NumberField
                  label="Communication update (minutes)"
                  value={incidents.communication_update_interval_minutes}
                  min={5}
                  max={1440}
                  onChange={(value) =>
                    setDraft({
                      ...draft,
                      incidents: { ...incidents, communication_update_interval_minutes: value },
                    })
                  }
                />
                <NumberField
                  label="Incident retention (days)"
                  value={incidents.incident_retention_days}
                  min={365}
                  max={3650}
                  onChange={(value) =>
                    setDraft({ ...draft, incidents: { ...incidents, incident_retention_days: value } })
                  }
                />
                <NumberField
                  label="Evidence retention (days)"
                  value={incidents.evidence_retention_days}
                  min={365}
                  max={3650}
                  onChange={(value) =>
                    setDraft({ ...draft, incidents: { ...incidents, evidence_retention_days: value } })
                  }
                />
              </div>
              <SaveButton saving={saving} onClick={save} />
            </SettingsPanel>
          )}

          {section === "appearance" && (
            <SettingsPanel
              title="Appearance"
              copy="This preference is personal to this browser and applies immediately across HIOP."
            >
              <div className="theme-choice">
                {(["light", "dark", "system"] as ThemePreference[]).map((value) => (
                  <button
                    key={value}
                    className={preference === value ? "active" : ""}
                    onClick={() => setPreference(value)}
                    aria-label={`Set theme to ${value}`}
                  >
                    <Icon name={value === "dark" ? "moon" : "sun"} aria-hidden="true" />
                    <strong>{value}</strong>
                    <span>
                      {value === "system"
                        ? "Follow operating system"
                        : `${value} interface`}
                    </span>
                  </button>
                ))}
              </div>
              <p className="settings-note">
                <Icon name="check" aria-hidden="true" />
                Royal blue is the primary interface accent; premium gold is reserved for
                hospitality highlights.
              </p>
            </SettingsPanel>
          )}

          {section === "security" && (
            <SettingsPanel
              title="Security posture"
              copy="Manage who can access your organisation."
            >
              <Link className="secondary-action" to="/administration/roles">Review roles and access</Link><Link className="secondary-action" to="/users">Manage team members</Link>
              <p className="settings-note">
                <Icon name="lock" aria-hidden="true" />
                Secret keys, password hashes, tokens and database credentials are never
                exposed here.
              </p>
            </SettingsPanel>
          )}

          {section === "health" && (
            <SettingsPanel
              title="System health"
              copy="Check service availability."
            >
              <button
                className="secondary-action"
                onClick={() => void refreshHealth()}
                aria-label="Refresh system health"
              >
                <Icon name="server" aria-hidden="true" />
                Refresh health
              </button>
              {health ? (
                <ReadOnlyGrid data={{availability:health.status,email:health.email}} />
              ) : (
                <Feedback loading />
              )}
            </SettingsPanel>
          )}

          {section === "maintenance" && (
            <SettingsPanel
              title="Backup & maintenance"
              copy="Get help with data recovery and planned maintenance."
            >
              <div className="maintenance-guide"><p>Backups and recovery are managed by the HIOP platform owner. Contact support if you need help recovering data.</p></div>
            </SettingsPanel>
          )}

          {section === "about" && (
            <SettingsPanel
              title="Application information"
              copy="Non-sensitive metadata reported by the running deployment."
            >
              <p><strong>HIOP</strong> helps your team manage devices, network monitoring, and IT operations across your organisation.</p><p className="settings-note">Application identity, version, and vendor metadata are read-only. Customer logo and organization details are managed under Administration → Organization.</p>
              <div className="module-list">
                <strong>Product pillars</strong>
                <span>Overview</span>
                <span>Discover</span>
                <span>Monitor</span>
                <span>Manage</span>
                <span>Automate</span>
                <span>Maintain</span>
                <span>Administration</span>
              </div>
            </SettingsPanel>
          )}
        </section>
      </div>
    </DashboardLayout>
  );
}

function SettingsPanel({
  title,
  copy,
  children,
}: {
  title: string;
  copy: string;
  children: React.ReactNode;
}) {
  return (
    <article className="settings-panel">
      <header>
        <div>
          <span>Configuration</span>
          <h2>{title}</h2>
          <p>{copy}</p>
        </div>
        <Icon name="settings" aria-hidden="true" />
      </header>
      <div className="settings-panel-body">{children}</div>
    </article>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
}) {
  return (
    <label>
      <span>{label}</span>
      <input
        required
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
}) {
  return (
    <label>
      <span>{label}</span>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: readonly (string | { value: string; label: string })[];
  onChange: (value: string) => void;
}) {
  return (
    <label>
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => typeof option === "string" ? (
          <option key={option}>{option}</option>
        ) : (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
    </label>
  );
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="settings-toggle">
      <span>{label}</span>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <i />
    </label>
  );
}

function SaveButton({ saving, onClick }: { saving: boolean; onClick: () => void }) {
  return (
    <div className="settings-save">
      <button className="primary-action" disabled={saving} onClick={onClick} aria-busy={saving}>
        {saving ? "Saving…" : "Save settings"}
      </button>
    </div>
  );
}

function ReadOnlyGrid({ data }: { data: Record<string, unknown> }) {
  return (
    <div className="settings-readonly">
      {Object.entries(data).map(([key, value]) => (
        <div key={key}>
          <dt>{key}</dt>
          <dd>{String(value)}</dd>
        </div>
      ))}
    </div>
  );
}

function HierarchySummary({
  title,
  copy,
  items,
  link,
}: {
  title: string;
  copy: string;
  items: Array<{ id: string; name: string; code?: string | null; type?: string | null; kind?: string | null; is_active?: boolean }>;
  link: string;
}) {
  return (
    <section className="panel hierarchy-summary">
      <header>
        <div>
          <h2>{title}</h2>
          <p>{copy}</p>
        </div>
        <Link className="primary-action" to={link}>Manage {title.toLowerCase()}</Link>
      </header>
      <p className="settings-note">Departments and locations created here are shared across HIOP. Discovered devices stay Unknown until you approve or assign them, or a naming rule matches them.</p>
      {!items.length ? (
        <Feedback empty="No items have been configured." />
      ) : (
        <div className="hierarchy-list clean-hierarchy-list">
          {items.map((item) => (
            <article key={item.id} className="hierarchy-card">
              <div>
                <strong>{item.name}</strong>
                <small>{item.code || item.type?.replaceAll("_", " ") || item.kind?.replaceAll("_", " ") || "Configured"}</small>
              </div>
              <span className={`status-pill ${item.is_active === false ? "neutral" : "success"}`}>{item.is_active === false ? "Inactive" : "Active"}</span>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
