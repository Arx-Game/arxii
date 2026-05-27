import { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAppSelector } from '@/store/hooks';
import { useIsAccountLoading } from '@/evennia_replacements/queries';

interface GuestOnlyRouteProps {
  children: ReactNode;
}

/**
 * Route guard that redirects authenticated users to the home page.
 * Used to prevent logged-in users from accessing login/register pages.
 *
 * Waits for the account query to settle before redirecting — see
 * StaffRoute for the race-condition rationale. (This is the guard that
 * actually closes the loop on that race: without the wait,
 * StaffRoute → /login → GuestOnlyRoute saw the account resolve and
 * bounced the user to / instead of letting StaffRoute re-evaluate.)
 */
export function GuestOnlyRoute({ children }: GuestOnlyRouteProps) {
  const isLoading = useIsAccountLoading();
  const account = useAppSelector((state) => state.auth.account);

  if (isLoading) {
    return null;
  }

  if (account) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
