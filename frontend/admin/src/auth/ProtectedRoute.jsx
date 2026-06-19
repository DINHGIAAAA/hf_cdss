import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

export function ProtectedRoute({ children, roles = [] }) {
  const { isAuthenticated, hasRole } = useAuth();
  const location = useLocation();

  if (!isAuthenticated) {
    return <Navigate replace state={{ from: location.pathname }} to="/login" />;
  }

  if (roles.length > 0 && !roles.some((role) => hasRole(role))) {
    return (
      <div className="access-denied" role="alert">
        <h1>Access denied</h1>
        <p>You need one of these roles: {roles.join(", ")}.</p>
      </div>
    );
  }

  return children;
}
