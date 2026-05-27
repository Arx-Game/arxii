import { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuthStatus } from '@/evennia_replacements/queries';

interface GuestOnlyRouteProps {
  children: ReactNode;
}

/**
 * Route guard that redirects authenticated users to the home page.
 * Used to prevent logged-in users from accessing login/register pages.
 *
 * See useAuthStatus for the race-condition rationale — this is the
 * guard that actually closed the loop on the bug (it would see the
 * account resolve mid-redirect and bounce the user to / instead of
 * letting the upstream guard re-evaluate to the correct destination).
 */
export function GuestOnlyRoute({ children }: GuestOnlyRouteProps) {
  const { isLoading, account } = useAuthStatus();

  if (isLoading) {
    return null;
  }

  if (account) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
