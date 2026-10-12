import { type ReactNode } from "react";
import { HashRouter, Navigate, Route, Routes } from "react-router-dom";

import AppShell from "@/components/layout/AppShell";
import { AppStateProvider } from "@/hooks/use-app-state";
import { AuthProvider, useAuth } from "@/lib/auth";
import Approvals from "@/pages/Approvals";
import Budgets from "@/pages/Budgets";
import Login from "@/pages/Login";
import Outcomes from "@/pages/Outcomes";
import Pipeline from "@/pages/Pipeline";
import Questions from "@/pages/Questions";
import RolesResumes from "@/pages/RolesResumes";
import SettingsPage from "@/pages/SettingsPage";

function Protected({ children }: { children: ReactNode }) {
  const { authed, ready } = useAuth();
  if (!ready) return null;
  if (!authed) return <Navigate to="/login" replace />;
  return <AppShell>{children}</AppShell>;
}

function Shell() {
  const { authed, ready } = useAuth();
  return (
    <Routes>
      <Route path="/login" element={ready && authed ? <Navigate to="/" replace /> : <Login />} />
      <Route path="/" element={<Protected><Pipeline /></Protected>} />
      <Route path="/approvals" element={<Protected><Approvals /></Protected>} />
      <Route path="/questions" element={<Protected><Questions /></Protected>} />
      <Route path="/roles" element={<Protected><RolesResumes /></Protected>} />
      <Route path="/budgets" element={<Protected><Budgets /></Protected>} />
      <Route path="/outcomes" element={<Protected><Outcomes /></Protected>} />
      <Route path="/settings" element={<Protected><SettingsPage /></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      {/* One poll + one event stream for the whole session: it lives here, above the routes, so
         switching pages never tears it down and reopens it. */}
      <AppStateProvider>
        <HashRouter>
          <Shell />
        </HashRouter>
      </AppStateProvider>
    </AuthProvider>
  );
}
