import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./auth/AuthContext";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { ADMIN_ROLES } from "./auth/roles";
import { ConversationsProvider } from "./conversations/ConversationsContext.jsx";
import { LanguageProvider } from "./i18n/LanguageProvider.jsx";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AdminLayout } from "./layouts/AdminLayout";

import { ApiExplorerPage } from "./pages/ApiExplorerPage";
import { AuditPage } from "./pages/AuditPage.jsx";
import { ChatPage } from "./pages/ChatPage";
import { EvidencePage } from "./pages/EvidencePage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { DoseRulesPage } from "./pages/DoseRulesPage.jsx";
import { DoseSafetyWarningsPage } from "./pages/DoseSafetyWarningsPage.jsx";
import { GdmtPoliciesPage } from "./pages/GdmtPoliciesPage.jsx";
import { InteractionRulesPage } from "./pages/InteractionRulesPage.jsx";
import { RulesPage } from "./pages/RulesPage";
import { SystemPage } from "./pages/SystemPage";
import { UsersPage } from "./pages/UsersPage";

function App() {
  return (
    <AuthProvider>
      <LanguageProvider>
        <ConversationsProvider>
          <TooltipProvider delayDuration={200}>
            <BrowserRouter>
              <Routes>
                <Route element={<LoginPage />} path="/login" />
                <Route element={<HomePage />} path="/" />
                <Route element={<ProtectedRoute><ChatPage /></ProtectedRoute>} path="/chat" />

                <Route
                  element={
                    <ProtectedRoute roles={ADMIN_ROLES}>
                      <AdminLayout />
                    </ProtectedRoute>
                  }
                  path="/admin"
                >
                  <Route element={<Navigate replace to="rules" />} index />
                  <Route element={<RulesPage />} path="rules" />
                  <Route element={<DoseRulesPage />} path="dose-rules" />
                  <Route element={<DoseSafetyWarningsPage />} path="dose-safety-warnings" />
                  <Route element={<InteractionRulesPage />} path="interaction-rules" />
                  <Route element={<GdmtPoliciesPage />} path="gdmt-policies" />
                  <Route element={<EvidencePage />} path="evidence" />
                  <Route element={<SystemPage />} path="system" />
                  <Route element={<UsersPage />} path="users" />
                  <Route element={<AuditPage />} path="audit" />
                  <Route element={<ApiExplorerPage />} path="api" />
                </Route>

                <Route element={<Navigate replace to="/login" />} path="*" />
              </Routes>
            </BrowserRouter>
          </TooltipProvider>
        </ConversationsProvider>
      </LanguageProvider>
    </AuthProvider>
  );
}

export default App;
