import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/AppShell";
import { api, clearCsrf, type Me } from "@/lib/api";
import { AuditPage } from "@/pages/AuditPage";
import { HomePage } from "@/pages/HomePage";
import { LoginPage } from "@/pages/LoginPage";
import { RolesPage } from "@/pages/RolesPage";
import { SequencesPage } from "@/pages/SequencesPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { ConsultPage } from "@/pages/ConsultPage";
import { BillingPage } from "@/pages/BillingPage";
import { ProceduresPage } from "@/pages/ProceduresPage";
import { QueuePage } from "@/pages/QueuePage";
import { RegisterPage } from "@/pages/RegisterPage";
import { UsersPage } from "@/pages/UsersPage";

function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: () => api<Me>("/auth/me"),
    retry: false,
  });
}

export default function App() {
  const qc = useQueryClient();
  const { data: me, isLoading, isError, refetch } = useMe();

  if (isLoading) {
    return <div className="flex min-h-screen items-center justify-center">Loading…</div>;
  }

  if (isError || !me) {
    return (
      <LoginPage
        onLoggedIn={(user) => {
          qc.setQueryData(["me"], user);
        }}
      />
    );
  }

  return (
    <Routes>
      <Route
        element={
          <AppShell
            me={me}
            onLogout={() => {
              clearCsrf();
              qc.setQueryData(["me"], null);
              void qc.invalidateQueries({ queryKey: ["me"] });
            }}
            onFacilityChange={() => {
              void refetch();
            }}
          />
        }
      >
        <Route path="/" element={<HomePage me={me} />} />
        <Route path="/settings" element={<SettingsPage me={me} />} />
        <Route path="/users" element={<UsersPage />} />
        <Route path="/roles" element={<RolesPage />} />
        <Route path="/sequences" element={<SequencesPage />} />
        <Route path="/audit" element={<AuditPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/queue" element={<QueuePage />} />
        <Route path="/consult" element={<ConsultPage />} />
        <Route path="/billing" element={<BillingPage />} />
        <Route path="/procedures" element={<ProceduresPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
