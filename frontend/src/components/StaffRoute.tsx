import { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAppSelector } from '@/store/hooks';
import { useIsAccountLoading } from '@/evennia_replacements/queries';

interface StaffRouteProps {
  children: ReactNode;
}

/**
 * Route guard that redirects non-staff users. Checks both authentication
 * and is_staff before rendering children, preventing unnecessary API calls.
 *
 * Waits for the account query to settle before deciding — without that
 * gate, direct URL navigation (e.g. typing /staff/missions in the
 * address bar) races: Redux is null on first render → guard redirects
 * to /login → GuestOnlyRoute sees the account resolve and bounces to /
 * → user lands on the home page instead of the requested staff page.
 */
export function StaffRoute({ children }: StaffRouteProps) {
  const isLoading = useIsAccountLoading();
  const account = useAppSelector((state) => state.auth.account);

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
