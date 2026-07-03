import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./auth/AuthContext";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { ADMIN_ROLES } from "./auth/roles";
import { AdminLayout } from "./layouts/AdminLayout";
import { ApiExplorerPage } from "./pages/ApiExplorerPage";
import { AuditPage } from "./pages/AuditPage.jsx";
import { ChatPage } from "./pages/ChatPage";
import { EvidencePage } from "./pages/EvidencePage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { DoseRulesPage } from "./pages/DoseRulesPage.jsx";
import { InteractionRulesPage } from "./pages/InteractionRulesPage.jsx";
import { RulesPage } from "./pages/RulesPage";
import { SystemPage } from "./pages/SystemPage";
import { UsersPage } from "./pages/UsersPage";

import "./styles/base.css";
import "./styles/layout.css";
import "./styles/sidebar.css";
import "./styles/chat.css";
import "./styles/clinical-panel.css";
import "./styles/modal.css";
import "./styles/admin.css";
import "./styles/login.css";

function App() {
  return (
    <AuthProvider>
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
            <Route element={<InteractionRulesPage />} path="interaction-rules" />
            <Route element={<EvidencePage />} path="evidence" />
            <Route element={<SystemPage />} path="system" />
            <Route element={<UsersPage />} path="users" />
            <Route element={<AuditPage />} path="audit" />
            <Route element={<ApiExplorerPage />} path="api" />
          </Route>

          <Route element={<Navigate replace to="/login" />} path="*" />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
