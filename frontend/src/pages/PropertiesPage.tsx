import { useEffect,useState,type FormEvent } from "react";
import { Feedback } from "../components/Feedback";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import { usePropertyAccessNotification } from "../hooks/usePropertyAccessNotification";
import { Toast } from "../components/Toast";
import { useRequest } from "../hooks/useRequest";
import type { ManagedProperty,User } from "../lib/types";
import { PageTitle } from "./DashboardPage";

const blank={name:"",code:"",address:"",city:"",state:"",country:"Nigeria",timezone:"Africa/Lagos",contact_email:"",contact_phone:"",description:""};
export default function PropertiesPage(){
  const [items, setItems] = useState<ManagedProperty[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [form, setForm] = useState(blank);
  const [access, setAccess] = useState({ property_id: "", user_id: "", access_level: "property_viewer", is_default: false });
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const { notifications, loading: notifLoading } = usePropertyAccessNotification();
  const me = useRequest(endpoints.me, []);
  const isAdmin = me.data?.role === "admin" || me.data?.role === "platformadmin";
  const load=async()=>{setLoading(true);try{const [properties,accounts]=await Promise.all([endpoints.managedProperties(),endpoints.users()]);setItems(properties);setUsers(accounts)}catch(e){setError(e instanceof Error?e.message:"Unable to load properties")}finally{setLoading(false)}};
  useEffect(()=>{let active=true;Promise.all([endpoints.managedProperties(),endpoints.users()]).then(([properties,accounts])=>{if(active){setItems(properties);setUsers(accounts)}}).catch(e=>{if(active)setError(e instanceof Error?e.message:"Unable to load properties")}).finally(()=>{if(active)setLoading(false)});return()=>{active=false}},[]);
  const run=async(action:()=>Promise<unknown>,message:string)=>{setError("");try{await action();setNotice(message);await load()}catch(e){setError(e instanceof Error?e.message:"Unable to save property")}};
  const create=(e:FormEvent)=>{e.preventDefault();void run(()=>endpoints.createManagedProperty(form),"Property created.");setForm(blank)};
  const assign=(e:FormEvent)=>{e.preventDefault();void run(()=>endpoints.assignPropertyAccess(access.property_id,access),"Property access assigned.")};
  return <DashboardLayout>
    <PageTitle eyebrow="V4J multi-property management" title="Properties" copy="Create hotels, review explainable operational health, and control user access within this organization."/>
    {error&&<Feedback error={error}/> } {notice&&<Toast message={notice}/>}{!notifLoading && notifications.length>0 && <Toast message="You have new property access notifications"/>}
    <section className="organization-grid">
      <form className="settings-panel settings-panel-body settings-form-grid" onSubmit={create}>
        <h2>Add property</h2>
        {(["name","code","address","city","state","country","timezone","contact_email","contact_phone","description"] as const).map(key=>(
          <label key={key}>
            <span>{key.replaceAll("_"," ")}</span>
            <input required={key==="name"} value={form[key]} onChange={e=>setForm({...form,[key]:e.target.value})}/>
          </label>
        ))}
        <button className="primary-action">Create property</button>
      </form>
      {isAdmin && (
        <form className="settings-panel settings-panel-body settings-form-grid" onSubmit={assign}>
          <h2>Assign property access</h2>
          <label>
            <span>Property</span>
            <select required value={access.property_id} onChange={e=>setAccess({...access,property_id:e.target.value})}>
              <option value="">Select property</option>
              {items.map(x=> <option key={x.id} value={x.id}>{x.name}</option>)}
            </select>
          </label>
          <label>
            <span>User</span>
            <select required value={access.user_id} onChange={e=>setAccess({...access,user_id:e.target.value})}>
              <option value="">Select user</option>
              {users.map(x=> <option key={x.id} value={x.id}>{x.username}</option>)}
            </select>
          </label>
          <label>
            <span>Access level</span>
            <select value={access.access_level} onChange={e=>setAccess({...access,access_level:e.target.value})}>
              {["property_viewer","property_technician","property_admin"].map(x=> <option key={x}>{x}</option>)}
            </select>
          </label>
          <label>
            <input type="checkbox" checked={access.is_default} onChange={e=>setAccess({...access,is_default:e.target.checked})}/> Default property
          </label>
          <button className="primary-action">Assign access</button>
        </form>
      )}
    </section>
    {loading?<Feedback loading/>:
      <section className="panel data-panel property-list-panel">
        <div className="property-table-wrap">
          <table className="property-table">
            <thead>
              <tr>
                <th>Property</th>
                <th>Status</th>
                <th>Assets</th>
                <th>Devices</th>
                <th>Availability</th>
                <th>Open incidents</th>
                <th>Health</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {items.map(x=>(
                <tr key={x.id}>
                  <td data-label="Property"><strong>{x.name}</strong><small>{x.code||"No code"} · {x.city||"Location unknown"}</small></td>
                  <td data-label="Status"><span className={`status-pill ${x.status==="active"?"success":"neutral"}`}>{x.status}</span></td>
                  <td data-label="Assets">{x.assets}</td>
                  <td data-label="Devices">{x.devices}</td>
                  <td data-label="Availability">{x.availability==null?"Insufficient data":`${x.availability}%`}</td>
                  <td data-label="Open incidents">{x.open_incidents}</td>
                  <td data-label="Health"><span className={`status-pill ${x.health==="healthy"?"success":x.health==="attention_required"?"danger":"neutral"}`}>{x.health.replaceAll("_"," ")}</span></td>
                  <td data-label="Action"><button className="secondary-action" onClick={()=>void run(()=>endpoints.setManagedPropertyStatus(x.id,x.status!=="active"),`Property ${x.status==="active"?"deactivated":"activated"}.`)}>{x.status==="active"?"Deactivate":"Activate"}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    }
  </DashboardLayout>;
}
