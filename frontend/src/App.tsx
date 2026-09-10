import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { Feedback } from "./components/Feedback";
import { hasUsableToken } from "./lib/auth";
import { endpoints } from "./lib/api";
import type { User } from "./lib/types";

const LoginPage = lazy(() => import("./pages/LoginPage"));
const PublicHomePage = lazy(() => import("./pages/PublicHomePage"));
const FeaturesPage = lazy(() => import("./pages/FeaturesPage"));
const PricingPage = lazy(() => import("./pages/PricingPage"));
const GetStartedPage = lazy(() => import("./pages/GetStartedPage"));
const OnboardingEntryPage = lazy(() => import("./pages/OnboardingEntryPage"));
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
const NetworkPerformancePage = lazy(() => import("./pages/NetworkPerformancePage"));
const AdministrationPage = lazy(() => import("./pages/AdministrationPage"));
const IntegrationsPage = lazy(() => import("./pages/IntegrationsPage"));
const AlertsPage = lazy(() => import("./pages/AlertsPage"));
const AssetFormPage = lazy(() => import("./pages/AssetFormPage"));
const AssetDetailsPage = lazy(() => import("./pages/AssetDetailsPage"));
const PlatformControlCenterPage = lazy(() => import("./pages/PlatformControlCenterPage"));
const ProcurementPage = lazy(() => import("./pages/ProcurementPage"));
const VendorsPage = lazy(() => import("./pages/VendorsPage"));
const OrganizationStructurePage = lazy(() => import("./pages/OrganizationStructurePage"));
const ProblemsPage = lazy(() => import("./pages/ProblemsPage"));
const ChangesPage = lazy(() => import("./pages/ChangesPage"));
const KnowledgePage = lazy(() => import("./pages/KnowledgePage"));
const ReportingPage = lazy(() => import("./pages/ReportingPage"));
const PropertiesPage = lazy(() => import("./pages/PropertiesPage"));
const BillingPage = lazy(() => import("./pages/BillingPage"));
const SNMPPage = lazy(() => import("./pages/SNMPPage"));
const LocalAgentsPage = lazy(() => import("./pages/LocalAgentsPage"));
const AccountAccessPage = lazy(() => import("./pages/AccountAccessPage"));

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

function ScrollToRouteTop() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (hash) {
      window.requestAnimationFrame(() => document.getElementById(hash.slice(1))?.scrollIntoView());
      return;
    }
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [pathname, hash]);
  return null;
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
  return <Suspense fallback={<Feedback loading />}><ScrollToRouteTop /><Routes>
    <Route path="/" element={<PublicHomePage />} />
    <Route path="/features" element={<FeaturesPage />} />
    <Route path="/pricing" element={<PricingPage />} />
    <Route path="/get-started" element={<GetStartedPage />} />
    <Route path="/login" element={<LoginPage />} />
    <Route path="/forgot-password" element={<AccountAccessPage mode="forgot" />} />
    <Route path="/reset-password" element={<AccountAccessPage mode="reset" />} />
    <Route path="/verify-email" element={<AccountAccessPage mode="verify" />} />
    <Route path="/accept-invitation" element={<AccountAccessPage mode="invitation" />} />
    <Route path="/app" element={protectedPage(<OnboardingEntryPage />)} />
    <Route path="/dashboard" element={protectedPage(<DashboardPage />)} />
    <Route path="/discover" element={<Navigate to="/discovery-intelligence" replace />} />
    <Route path="/discovery" element={<Navigate to="/discovery-intelligence" replace />} />
    <Route path="/agents" element={<Navigate to="/administration/agents" replace />} />
    <Route path="/billing" element={<Navigate to="/administration/billing" replace />} />
    <Route path="/organization" element={<Navigate to="/administration/organization" replace />} />
    <Route path="/org" element={<Navigate to="/administration/organization" replace />} />
    <Route path="/admin" element={<Navigate to="/administration" replace />} />
    <Route path="/audit" element={<Navigate to="/administration/audit" replace />} />
    <Route path="/platform-control" element={<Navigate to="/platform" replace />} />
    <Route path="/control-center" element={<Navigate to="/platform" replace />} />
    <Route path="/devices" element={protectedPage(<DevicesPage />)} />
    <Route path="/procurement" element={protectedPage(<ProcurementPage />)} />
    <Route path="/procurement/:id" element={protectedPage(<ProcurementPage />)} />
    <Route path="/vendors" element={protectedPage(<VendorsPage />)} />
    <Route path="/vendors/:id" element={protectedPage(<VendorsPage />)} />
    <Route path="/devices/new" element={<Navigate to="/assets/new" replace />} />
    <Route path="/assets/new" element={roleProtectedPage(<AssetFormPage />, ["admin"])} />
    <Route path="/assets/:id/edit" element={roleProtectedPage(<AssetFormPage />, ["admin"])} />
    <Route path="/assets/:id" element={protectedPage(<AssetDetailsPage />)} />
    <Route path="/devices/:id/edit" element={protectedPage(<EditDevicePage />)} />
    <Route path="/devices/:id" element={protectedPage(<DeviceDetailsPage />)} />
    <Route path="/network" element={protectedPage(<NetworkPage />)} />
    <Route path="/alerts" element={protectedPage(<AlertsPage />)} />
    <Route path="/snmp" element={protectedPage(<SNMPPage />)} />
    <Route path="/topology" element={protectedPage(<TopologyPage />)} />
    <Route path="/segmentation" element={protectedPage(<SegmentationPage />)} />
    <Route path="/network-performance" element={protectedPage(<NetworkPerformancePage />)} />
    <Route path="/discovery-intelligence/*" element={protectedPage(<DiscoveryIntelligencePage />)} />
    <Route path="/automation/*" element={protectedPage(<AutomationPage />)} />
    <Route path="/incidents" element={protectedPage(<IncidentsPage />)} />
    <Route path="/incidents/new" element={protectedPage(<IncidentsPage />)} />
    <Route path="/incidents/services" element={protectedPage(<IncidentsPage />)} />
    <Route path="/incidents/services/:serviceId" element={protectedPage(<IncidentsPage />)} />
    <Route path="/incidents/playbooks/*" element={protectedPage(<IncidentsPage />)} />
    <Route path="/incidents/:id/*" element={protectedPage(<IncidentsPage />)} />
    <Route path="/problems" element={protectedPage(<ProblemsPage />)} />
    <Route path="/problems/new" element={roleProtectedPage(<ProblemsPage />, ["admin"])} />
    <Route path="/problems/:id" element={protectedPage(<ProblemsPage />)} />
    <Route path="/changes" element={protectedPage(<ChangesPage />)} />
    <Route path="/changes/new" element={roleProtectedPage(<ChangesPage />, ["admin"])} />
    <Route path="/changes/:id" element={protectedPage(<ChangesPage />)} />
    <Route path="/knowledge" element={protectedPage(<KnowledgePage />)} />
    <Route path="/knowledge/new" element={roleProtectedPage(<KnowledgePage />, ["admin", "technician"])} />
    <Route path="/knowledge/:id" element={protectedPage(<KnowledgePage />)} />
    <Route path="/reports" element={protectedPage(<ReportingPage />)} />
    <Route path="/hierarchy" element={protectedPage(<HierarchyPage />)} />
    <Route path="/users" element={roleProtectedPage(<UsersPage />, ["admin"])} />
    <Route path="/users/new" element={roleProtectedPage(<UserFormPage mode="create" />, ["admin"])} />
    <Route path="/users/:id/edit" element={roleProtectedPage(<UserFormPage mode="edit" />, ["admin"])} />
    <Route path="/users/:id" element={roleProtectedPage(<UserDetailsPage />, ["admin"])} />
    <Route path="/settings" element={roleProtectedPage(<SettingsPage />, ["admin"])} />
    <Route path="/administration" element={roleProtectedPage(<AdministrationPage />, ["admin"])} />
    <Route path="/administration/roles" element={roleProtectedPage(<AdministrationPage />, ["admin"])} />
    <Route path="/administration/audit" element={roleProtectedPage(<AdministrationPage />, ["admin"])} />
    <Route path="/administration/integrations" element={roleProtectedPage(<IntegrationsPage />, ["admin"])} />
    <Route path="/administration/organization" element={roleProtectedPage(<OrganizationStructurePage />, ["admin"])} />
    <Route path="/administration/properties" element={roleProtectedPage(<PropertiesPage />, ["admin"])} />
    <Route path="/administration/billing" element={roleProtectedPage(<BillingPage />, ["admin"])} />
    <Route path="/administration/agents" element={roleProtectedPage(<LocalAgentsPage />, ["admin"])} />
    <Route path="/platform/*" element={roleProtectedPage(<PlatformControlCenterPage />, ["platformadmin"])} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></Suspense>;
}
