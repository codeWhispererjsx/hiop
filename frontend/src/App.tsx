import { lazy, Suspense, useEffect, type ReactNode } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { Feedback } from "./components/Feedback";
import { hasUsableToken } from "./lib/auth";

const LoginPage = lazy(() => import("./pages/LoginPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const DevicesPage = lazy(() => import("./pages/DevicesPage"));
const DeviceDetailsPage = lazy(() => import("./pages/DeviceDetailsPage"));
const AddDevicePage = lazy(() => import("./pages/AddDevicePage"));
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

function Protected({ children }: { children: ReactNode }) {
  return hasUsableToken() ? children : <Navigate to="/login" replace />;
}

export default function App() {
  const navigate = useNavigate();
  useEffect(() => {
    const unauthorized = () => navigate("/login", { replace: true });
    window.addEventListener("hiop:unauthorized", unauthorized);
    return () => window.removeEventListener("hiop:unauthorized", unauthorized);
  }, [navigate]);

  const protectedPage = (page: ReactNode) => <Protected>{page}</Protected>;
  return <Suspense fallback={<Feedback loading />}><Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route path="/dashboard" element={protectedPage(<DashboardPage />)} />
    <Route path="/devices" element={protectedPage(<DevicesPage />)} />
    <Route path="/devices/new" element={protectedPage(<AddDevicePage />)} />
    <Route path="/devices/:id/edit" element={protectedPage(<EditDevicePage />)} />
    <Route path="/devices/:id" element={protectedPage(<DeviceDetailsPage />)} />
    <Route path="/network" element={protectedPage(<NetworkPage />)} />
    <Route path="/topology" element={protectedPage(<TopologyPage />)} />
    <Route path="/discovery-intelligence/*" element={protectedPage(<DiscoveryIntelligencePage />)} />
    <Route path="/automation/*" element={protectedPage(<AutomationPage />)} />
    <Route path="/incidents" element={protectedPage(<IncidentsPage />)} />
    <Route path="/incidents/new" element={protectedPage(<IncidentsPage />)} />
    <Route path="/incidents/playbooks/*" element={protectedPage(<IncidentsPage />)} />
    <Route path="/incidents/:id/*" element={protectedPage(<IncidentsPage />)} />
    <Route path="/hierarchy" element={protectedPage(<HierarchyPage />)} />
    <Route path="/users" element={protectedPage(<UsersPage />)} />
    <Route path="/users/new" element={protectedPage(<UserFormPage mode="create" />)} />
    <Route path="/users/:id/edit" element={protectedPage(<UserFormPage mode="edit" />)} />
    <Route path="/users/:id" element={protectedPage(<UserDetailsPage />)} />
    <Route path="/settings" element={protectedPage(<SettingsPage />)} />
    <Route path="/" element={<Navigate to="/dashboard" replace />} />
    <Route path="*" element={<Navigate to="/dashboard" replace />} />
  </Routes></Suspense>;
}
