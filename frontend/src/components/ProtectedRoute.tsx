import { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuthStatus } from '@/evennia_replacements/queries';

interface ProtectedRouteProps {
  children: ReactNode;
}

/**
 * Route guard that redirects unauthenticated users to the login page.
 * See useAuthStatus for the race-condition rationale.
 */
export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { isLoading, account } = useAuthStatus();

  if (isLoading) {
    return null;
  }

  if (!account) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
