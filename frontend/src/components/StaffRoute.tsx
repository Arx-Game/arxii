import { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAppSelector } from '@/store/hooks';

interface StaffRouteProps {
  children: ReactNode;
}

/**
 * Route guard that redirects non-staff users. Checks both authentication
 * and is_staff before rendering children, preventing unnecessary API calls.
 */
export function StaffRoute({ children }: StaffRouteProps) {
  const account = useAppSelector((state) => state.auth.account);

  if (!account) {
    return <Navigate to="/login" replace />;
  }

  if (!account.is_staff) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
