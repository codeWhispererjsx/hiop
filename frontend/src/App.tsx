import { lazy, Suspense, useEffect, type ReactNode } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { Feedback } from "./components/Feedback";

const LoginPage = lazy(() => import("./pages/LoginPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const ReportsPage = lazy(() => import("./pages/ReportsPage"));
const DevicesPage = lazy(() => import("./pages/DevicesPage"));
const DeviceDetailsPage = lazy(() => import("./pages/DeviceDetailsPage"));
const AddDevicePage = lazy(() => import("./pages/AddDevicePage"));
const EditDevicePage = lazy(() => import("./pages/EditDevicePage"));
const NetworkPage = lazy(() => import("./pages/NetworkPage"));
const AlertsPage = lazy(() => import("./pages/AlertsPage"));
const TicketsPage = lazy(() => import("./pages/TicketsPage"));
const TicketDetailsPage = lazy(() => import("./pages/TicketDetailsPage"));
const TicketFormPage = lazy(() => import("./pages/TicketFormPage"));
const HierarchyPage = lazy(() => import("./pages/HierarchyPage"));
const UsersPage = lazy(() => import("./pages/UsersPage"));
const UserDetailsPage = lazy(() => import("./pages/UserDetailsPage"));
const UserFormPage = lazy(() => import("./pages/UserFormPage"));
const AuditPage = lazy(() => import("./pages/AuditPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));

function Protected({ children }: { children: ReactNode }) {
  return localStorage.getItem("hiop_token") ? children : <Navigate to="/login" replace />;
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
    <Route path="/reports" element={protectedPage(<ReportsPage />)} />
    <Route path="/devices" element={protectedPage(<DevicesPage />)} />
    <Route path="/devices/new" element={protectedPage(<AddDevicePage />)} />
    <Route path="/devices/:id/edit" element={protectedPage(<EditDevicePage />)} />
    <Route path="/devices/:id" element={protectedPage(<DeviceDetailsPage />)} />
    <Route path="/network" element={protectedPage(<NetworkPage />)} />
    <Route path="/alerts" element={protectedPage(<AlertsPage />)} />
    <Route path="/tickets" element={protectedPage(<TicketsPage />)} />
    <Route path="/tickets/new" element={protectedPage(<TicketFormPage mode="create" />)} />
    <Route path="/tickets/:id/edit" element={protectedPage(<TicketFormPage mode="edit" />)} />
    <Route path="/tickets/:id" element={protectedPage(<TicketDetailsPage />)} />
    <Route path="/hierarchy" element={protectedPage(<HierarchyPage />)} />
    <Route path="/users" element={protectedPage(<UsersPage />)} />
    <Route path="/users/new" element={protectedPage(<UserFormPage mode="create" />)} />
    <Route path="/users/:id/edit" element={protectedPage(<UserFormPage mode="edit" />)} />
    <Route path="/users/:id" element={protectedPage(<UserDetailsPage />)} />
    <Route path="/audit" element={protectedPage(<AuditPage />)} />
    <Route path="/settings" element={protectedPage(<SettingsPage />)} />
    <Route path="/" element={<Navigate to="/dashboard" replace />} />
    <Route path="*" element={<Navigate to="/dashboard" replace />} />
  </Routes></Suspense>;
}
