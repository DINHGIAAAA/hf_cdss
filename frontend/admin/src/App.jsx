import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./auth/AuthContext";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { AdminLayout } from "./layouts/AdminLayout";
import { LoginPage } from "./pages/LoginPage";
import { ApiExplorerPage } from "./pages/ApiExplorerPage";
import { EvidencePage } from "./pages/EvidencePage";
import { DoseRulesPage } from "./pages/DoseRulesPage.jsx";
import { InteractionRulesPage } from "./pages/InteractionRulesPage.jsx";
import { RulesPage } from "./pages/RulesPage";
import { SystemPage } from "./pages/SystemPage";

import "./styles/base.css";
import "./styles/admin.css";
import "./styles/login.css";

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<LoginPage />} path="/login" />
          <Route
            element={
              <ProtectedRoute>
                <AdminLayout />
              </ProtectedRoute>
            }
            path="/"
          >
            <Route element={<Navigate replace to="rules" />} index />
            <Route element={<RulesPage />} path="rules" />
            <Route element={<DoseRulesPage />} path="dose-rules" />
            <Route element={<InteractionRulesPage />} path="interaction-rules" />
            <Route element={<EvidencePage />} path="evidence" />
            <Route element={<SystemPage />} path="system" />
            <Route element={<ApiExplorerPage />} path="api" />
          </Route>
          <Route element={<Navigate replace to="/rules" />} path="*" />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
