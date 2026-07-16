import { useMemo, useState, type FormEvent } from "react";
import { Feedback } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import type {
  HierarchyCatalog,
  HierarchyItem,
  HierarchyKind,
} from "../lib/types";
import { PageTitle } from "./DashboardPage";

const sections: Array<{
  kind: HierarchyKind;
  key: keyof HierarchyCatalog;
  label: string;
  parent?: keyof HierarchyCatalog;
}> = [
  { kind: "properties", key: "properties", label: "Properties" },
  {
    kind: "buildings",
    key: "buildings",
    label: "Buildings",
    parent: "properties",
  },
  { kind: "floors", key: "floors", label: "Floors", parent: "buildings" },
  { kind: "rooms", key: "rooms", label: "Rooms", parent: "floors" },
  {
    kind: "departments",
    key: "departments",
    label: "Departments",
    parent: "properties",
  },
  {
    kind: "network-zones",
    key: "network_zones",
    label: "Network zones",
    parent: "properties",
  },
];

const blank = {
  name: "",
  parent_id: "",
  code: "",
  address: "",
  cidr: "",
  vlan_id: "",
};

export default function HierarchyPage() {
  const request = useRequest(endpoints.hierarchy, []);
  const [selected, setSelected] = useState(0);
  const [draft, setDraft] = useState(blank);
  const [editing, setEditing] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const section = sections[selected];
  const catalog = request.data;
  const rows = catalog?.[section.key] ?? [];
  const parents = useMemo(
    () =>
      section.parent && catalog
        ? catalog[section.parent].filter((row) => row.is_active)
        : [],
    [catalog, section.parent],
  );
  const parentNames = useMemo(
    () => new Map(parents.map((row) => [row.id, row.name])),
    [parents],
  );

  const reset = () => {
    setDraft(blank);
    setEditing(null);
  };
  const edit = (row: HierarchyItem) => {
    setEditing(row.id);
    setDraft({
      name: row.name,
      parent_id: row.parent_id ?? "",
      code: row.code ?? "",
      address: row.address ?? "",
      cidr: row.cidr ?? "",
      vlan_id: row.vlan_id?.toString() ?? "",
    });
  };
  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!draft.name.trim()) {
      setNotice("Name is required.");
      return;
    }
    const payload: Partial<HierarchyItem> = {
      name: draft.name.trim(),
      is_active: true,
      parent_id: draft.parent_id || null,
    };
    if (section.kind === "properties")
      Object.assign(payload, {
        code: draft.code.trim() || null,
        address: draft.address.trim() || null,
      });
    if (section.kind === "network-zones")
      Object.assign(payload, {
        cidr: draft.cidr.trim() || null,
        vlan_id: draft.vlan_id ? Number(draft.vlan_id) : null,
      });
    setSaving(true);
    setNotice("");
    try {
      if (editing)
        await endpoints.updateHierarchy(section.kind, editing, payload);
      else await endpoints.createHierarchy(section.kind, payload);
      await request.reload();
      reset();
      setNotice(`${section.label.slice(0, -1)} saved.`);
    } catch (error) {
      setNotice(
        error instanceof Error ? error.message : "Unable to save record.",
      );
    } finally {
      setSaving(false);
    }
  };
  const deactivate = async (row: HierarchyItem) => {
    if (
      !window.confirm(
        `Deactivate ${row.name}? Existing device links will be retained.`,
      )
    )
      return;
    try {
      await endpoints.deactivateHierarchy(section.kind, row.id);
      await request.reload();
      setNotice(`${row.name} was deactivated.`);
    } catch (error) {
      setNotice(
        error instanceof Error ? error.message : "Unable to deactivate record.",
      );
    }
  };

  return (
    <DashboardLayout>
      <PageTitle
        eyebrow="Inventory structure"
        title="Locations & structure"
        copy="Manage the real property, location, department, and network hierarchy used by device inventory."
      />
      {request.loading || request.error || !catalog ? (
        <Feedback
          loading={request.loading}
          error={request.error}
          onRetry={request.reload}
        />
      ) : (
        <>
          <nav
            className="detail-tabs hierarchy-tabs"
            aria-label="Hierarchy sections"
          >
            {sections.map((item, index) => (
              <button
                key={item.kind}
                className={selected === index ? "active" : ""}
                onClick={() => {
                  setSelected(index);
                  reset();
                  setNotice("");
                }}
              >
                {item.label} <span>{catalog[item.key].length}</span>
              </button>
            ))}
          </nav>
          {notice && (
            <div className="inline-notice" role="status">
              {notice}
            </div>
          )}
          <section className="hierarchy-layout">
            <article className="panel hierarchy-list">
              <header className="section-head">
                <div>
                  <h2>{section.label}</h2>
                  <p>
                    Inactive records remain available for historical device
                    relationships.
                  </p>
                </div>
              </header>
              {rows.length ? (
                <div className="compact-list">
                  {rows.map((row) => (
                    <div key={row.id}>
                      <span
                        className={`pulse ${row.is_active ? "online" : ""}`}
                      />
                      <strong>{row.name}</strong>
                      <span>
                        {row.parent_id
                          ? (parentNames.get(row.parent_id) ??
                            "Parent unavailable")
                          : "No parent assigned"}
                      </span>
                      <span>{row.is_active ? "Active" : "Inactive"}</span>
                      <span className="row-actions">
                        <button
                          aria-label={`Edit ${row.name}`}
                          onClick={() => edit(row)}
                        >
                          <Icon name="audit" size={15} />
                        </button>
                        {row.is_active && (
                          <button
                            aria-label={`Deactivate ${row.name}`}
                            onClick={() => void deactivate(row)}
                          >
                            <Icon name="close" size={15} />
                          </button>
                        )}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <Feedback
                  emptyTitle={`No ${section.label.toLowerCase()}`}
                  empty="Create the first record using the form."
                />
              )}
            </article>
            <form className="panel hierarchy-form" onSubmit={save}>
              <div className="section-head">
                <div>
                  <h2>
                    {editing ? "Edit" : "Add"} {section.label.slice(0, -1)}
                  </h2>
                  <p>
                    Changes are stored in PostgreSQL and recorded in the audit
                    trail.
                  </p>
                </div>
              </div>
              <div className="hierarchy-form-body">
                <label>
                  Name
                  <input
                    value={draft.name}
                    maxLength={120}
                    onChange={(e) =>
                      setDraft({ ...draft, name: e.target.value })
                    }
                    disabled={saving}
                  />
                </label>
                {section.parent && (
                  <label>
                    Parent
                    <select
                      value={draft.parent_id}
                      onChange={(e) =>
                        setDraft({ ...draft, parent_id: e.target.value })
                      }
                      disabled={saving}
                    >
                      <option value="">No parent assigned</option>
                      {parents.map((row) => (
                        <option key={row.id} value={row.id}>
                          {row.name}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                {section.kind === "properties" && (
                  <>
                    <label>
                      Property code
                      <input
                        value={draft.code}
                        onChange={(e) =>
                          setDraft({ ...draft, code: e.target.value })
                        }
                      />
                    </label>
                    <label>
                      Address
                      <input
                        value={draft.address}
                        onChange={(e) =>
                          setDraft({ ...draft, address: e.target.value })
                        }
                      />
                    </label>
                  </>
                )}
                {section.kind === "network-zones" && (
                  <>
                    <label>
                      CIDR
                      <input
                        placeholder="10.50.20.0/24"
                        value={draft.cidr}
                        onChange={(e) =>
                          setDraft({ ...draft, cidr: e.target.value })
                        }
                      />
                    </label>
                    <label>
                      VLAN ID
                      <input
                        type="number"
                        min="1"
                        max="4094"
                        value={draft.vlan_id}
                        onChange={(e) =>
                          setDraft({ ...draft, vlan_id: e.target.value })
                        }
                      />
                    </label>
                  </>
                )}
                <footer>
                  {editing && (
                    <button
                      type="button"
                      className="secondary-action"
                      onClick={reset}
                    >
                      Cancel
                    </button>
                  )}
                  <button className="primary-action" disabled={saving}>
                    {saving ? "Saving..." : "Save record"}
                  </button>
                </footer>
              </div>
            </form>
          </section>
        </>
      )}
    </DashboardLayout>
  );
}
