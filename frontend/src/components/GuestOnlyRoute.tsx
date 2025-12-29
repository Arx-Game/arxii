import { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAppSelector } from '@/store/hooks';

interface GuestOnlyRouteProps {
  children: ReactNode;
}

/**
 * Route guard that redirects authenticated users to the home page.
 * Used to prevent logged-in users from accessing login/register pages.
 */
export function GuestOnlyRoute({ children }: GuestOnlyRouteProps) {
  const account = useAppSelector((state) => state.auth.account);

  if (account) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
