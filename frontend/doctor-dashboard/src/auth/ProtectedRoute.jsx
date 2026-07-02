import { Link, Navigate, useLocation } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

export function ProtectedRoute({ children, roles = [] }) {
  const { isAuthenticated, bootstrapping, hasRole } = useAuth();
  const location = useLocation();

  if (bootstrapping) {
    return (
      <div aria-busy="true" className="admin-empty" role="status">
        Checking session…
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate replace state={{ from: location.pathname }} to="/login" />;
  }

  if (roles.length > 0 && !roles.some((role) => hasRole(role))) {
    return (
      <div className="access-denied" role="alert">
        <h1>Access denied</h1>
        <p>You need one of these roles: {roles.join(", ")}.</p>
        <p>
          <Link to="/chat">Return to clinical chat</Link>
        </p>
      </div>
    );
  }

  return children;
}
