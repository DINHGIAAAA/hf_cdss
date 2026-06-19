import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { isAdminUser } from "../auth/roles";
import { ChatPage } from "./ChatPage";

export function HomePage() {
  const { isAuthenticated, user } = useAuth();
  const location = useLocation();

  if (!isAuthenticated) {
    return <Navigate replace state={{ from: location.pathname }} to="/login" />;
  }

  if (isAdminUser(user)) {
    return <Navigate replace to="/admin/rules" />;
  }

  return <ChatPage />;
}
