import { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuthStatus } from '@/evennia_replacements/queries';

interface GMRouteProps {
  children: ReactNode;
}

/**
 * Route guard that redirects users without GM reach. Reads auth state from
 * the React Query cache so the loading state and the resolved account
 * arrive in the same render - see useAuthStatus for the full
 * race-condition rationale.
 *
 * Every staff member counts as a GM here (#3565) - the Scenario Studio
 * under /stories/scenarios reuses the same staff-built editor pages
 * (MissionCanvasPage/NodePage/OptionPage) that /staff/missions already
 * mounts behind StaffRoute, so staff must still pass this gate too.
 */
export function GMRoute({ children }: GMRouteProps) {
  const { isLoading, account } = useAuthStatus();

  if (isLoading) {
    return null;
  }

  if (!account) {
    return <Navigate to="/login" replace />;
  }

  if (!account.is_gm && !account.is_staff) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
