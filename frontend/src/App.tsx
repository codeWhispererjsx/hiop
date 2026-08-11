import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { Feedback } from "./components/Feedback";
import { hasUsableToken } from "./lib/auth";
import { endpoints } from "./lib/api";
import type { User } from "./lib/types";

const LoginPage = lazy(() => import("./pages/LoginPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const DevicesPage = lazy(() => import("./pages/DevicesPage"));
const DeviceDetailsPage = lazy(() => import("./pages/DeviceDetailsPage"));
const EditDevicePage = lazy(() => import("./pages/EditDevicePage"));
const NetworkPage = lazy(() => import("./pages/NetworkPage"));
const HierarchyPage = lazy(() => import("./pages/HierarchyPage"));
const UsersPage = lazy(() => import("./pages/UsersPage"));
const UserDetailsPage = lazy(() => import("./pages/UserDetailsPage"));
const UserFormPage = lazy(() => import("./pages/UserFormPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const AutomationPage = lazy(() => import("./pages/AutomationPage"));
const IncidentsPage = lazy(() => import("./pages/IncidentsPage"));
const DiscoveryIntelligencePage = lazy(() => import("./pages/DiscoveryIntelligencePage"));
const TopologyPage = lazy(() => import("./pages/TopologyPage"));
const SegmentationPage = lazy(() => import("./pages/SegmentationPage"));
const AdministrationPage = lazy(() => import("./pages/AdministrationPage"));
const AlertsPage = lazy(() => import("./pages/AlertsPage"));
const AssetFormPage = lazy(() => import("./pages/AssetFormPage"));
const AssetDetailsPage = lazy(() => import("./pages/AssetDetailsPage"));
const PlatformControlCenterPage = lazy(() => import("./pages/PlatformControlCenterPage"));
const ProcurementPage = lazy(() => import("./pages/ProcurementPage"));

function Protected({ children }: { children: ReactNode }) {
  return hasUsableToken() ? children : <Navigate to="/login" replace />;
}

function RoleProtected({ children, roles }: { children: ReactNode; roles: User["role"][] }) {
  const [user, setUser] = useState<User | null>();
  useEffect(() => {
    let active = true;
    void endpoints.me().then((result) => { if (active) setUser(result); }).catch(() => { if (active) setUser(null); });
    return () => { active = false; };
  }, []);
  if (user === undefined) return <Feedback loading />;
  if (!user || !roles.includes(user.role)) return <Navigate to="/dashboard" replace />;
  return children;
}

export default function App() {
  const navigate = useNavigate();
  useEffect(() => {
    const unauthorized = () => navigate("/login", { replace: true });
    window.addEventListener("hiop:unauthorized", unauthorized);
    return () => window.removeEventListener("hiop:unauthorized", unauthorized);
  }, [navigate]);

  const protectedPage = (page: ReactNode) => <Protected>{page}</Protected>;
  const roleProtectedPage = (page: ReactNode, roles: User["role"][]) =>
    <Protected><RoleProtected roles={roles}>{page}</RoleProtected></Protected>;
  return <Suspense fallback={<Feedback loading />}><Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route path="/dashboard" element={protectedPage(<DashboardPage />)} />
    <Route path="/devices" element={protectedPage(<DevicesPage />)} />
    <Route path="/procurement" element={protectedPage(<ProcurementPage />)} />
    <Route path="/procurement/:id" element={protectedPage(<ProcurementPage />)} />
    <Route path="/devices/new" element={<Navigate to="/assets/new" replace />} />
    <Route path="/assets/new" element={roleProtectedPage(<AssetFormPage />, ["admin"])} />
    <Route path="/assets/:id/edit" element={roleProtectedPage(<AssetFormPage />, ["admin"])} />
    <Route path="/assets/:id" element={protectedPage(<AssetDetailsPage />)} />
    <Route path="/devices/:id/edit" element={protectedPage(<EditDevicePage />)} />
    <Route path="/devices/:id" element={protectedPage(<DeviceDetailsPage />)} />
    <Route path="/network" element={protectedPage(<NetworkPage />)} />
    <Route path="/alerts" element={protectedPage(<AlertsPage />)} />
    <Route path="/topology" element={protectedPage(<TopologyPage />)} />
    <Route path="/segmentation" element={protectedPage(<SegmentationPage />)} />
    <Route path="/discovery-intelligence/*" element={protectedPage(<DiscoveryIntelligencePage />)} />
    <Route path="/automation/*" element={protectedPage(<AutomationPage />)} />
    <Route path="/incidents" element={protectedPage(<IncidentsPage />)} />
    <Route path="/incidents/new" element={protectedPage(<IncidentsPage />)} />
    <Route path="/incidents/playbooks/*" element={protectedPage(<IncidentsPage />)} />
    <Route path="/incidents/:id/*" element={protectedPage(<IncidentsPage />)} />
    <Route path="/hierarchy" element={protectedPage(<HierarchyPage />)} />
    <Route path="/users" element={roleProtectedPage(<UsersPage />, ["admin"])} />
    <Route path="/users/new" element={roleProtectedPage(<UserFormPage mode="create" />, ["admin"])} />
    <Route path="/users/:id/edit" element={roleProtectedPage(<UserFormPage mode="edit" />, ["admin"])} />
    <Route path="/users/:id" element={roleProtectedPage(<UserDetailsPage />, ["admin"])} />
    <Route path="/settings" element={roleProtectedPage(<SettingsPage />, ["admin"])} />
    <Route path="/administration" element={roleProtectedPage(<AdministrationPage />, ["admin"])} />
    <Route path="/administration/roles" element={roleProtectedPage(<AdministrationPage />, ["admin"])} />
    <Route path="/administration/audit" element={roleProtectedPage(<AdministrationPage />, ["admin"])} />
    <Route path="/platform/*" element={roleProtectedPage(<PlatformControlCenterPage />, ["platformadmin"])} />
    <Route path="/" element={<Navigate to="/dashboard" replace />} />
    <Route path="*" element={<Navigate to="/dashboard" replace />} />
  </Routes></Suspense>;
}
