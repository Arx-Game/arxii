import { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAppSelector } from '@/store/hooks';
import { useIsAccountLoading } from '@/evennia_replacements/queries';

interface ProtectedRouteProps {
  children: ReactNode;
}

/**
 * Route guard that redirects unauthenticated users to the login page.
 * Used to protect pages that require authentication.
 *
 * Waits for the account query to settle before redirecting — see
 * StaffRoute for the race-condition rationale.
 */
export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const isLoading = useIsAccountLoading();
  const account = useAppSelector((state) => state.auth.account);

  if (isLoading) {
    return null;
  }

  if (!account) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
