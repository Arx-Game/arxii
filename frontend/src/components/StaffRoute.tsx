import { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuthStatus } from '@/evennia_replacements/queries';

interface StaffRouteProps {
  children: ReactNode;
}

/**
 * Route guard that redirects non-staff users. Reads auth state from
 * the React Query cache so the loading state and the resolved account
 * arrive in the same render — see useAuthStatus for the full
 * race-condition rationale.
 */
export function StaffRoute({ children }: StaffRouteProps) {
  const { isLoading, account } = useAuthStatus();

  if (isLoading) {
    return null;
  }

  if (!account) {
    return <Navigate to="/login" replace />;
  }

  if (!account.is_staff) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
